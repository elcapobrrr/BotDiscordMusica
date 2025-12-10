import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from yt_dlp import YoutubeDL
import logging

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN") # Token del bot en el .env tienes que poner tu token del bot de discord 

# Configurar ruta absoluta de FFmpeg dinámica
# Asumiendo estructura: carpeta_bot/ffmpeg/bin/ffmpeg.exe
FFMPEG_PATH = os.path.join(os.getcwd(), "ffmpeg", "bin", "ffmpeg.exe")
if not os.path.exists(FFMPEG_PATH):
    # Intentar búsqueda alternativa si no está en bin
    FFMPEG_PATH = os.path.join(os.getcwd(), "ffmpeg", "ffmpeg.exe")

if not os.path.exists(FFMPEG_PATH):
    print(f"[WARNING] No se encontró ffmpeg en {FFMPEG_PATH}. Asegúrate de que la carpeta existe.")


intents = discord.Intents.default() # Intents del bot
intents.message_content = False

bot = commands.Bot(command_prefix="!", intents=intents)

# Diccionario para guardar el source de audio por servidor
# Esto permite pausar y reanudar sin perder el source

# Diccionario para guardar el source de audio por servidor
# Esto permite pausar y reanudar sin perder el source
audio_sources = {}

# Cola por servidor: lista de dicts {"web_url":..., "title":..., "text_channel": ...}
audio_queues = {}

# Historial por servidor para comando "anterior"
audio_history = {}

# Configurar logging para ver más información
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s')


# Controles en mensaje: botones para reproducir/pausar/siguiente/anterior/stop
class PlayerControls(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.button(label="Anterior", style=discord.ButtonStyle.secondary, emoji="⏮️")
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = self.guild_id
        if interaction.guild is None or interaction.guild.id != gid:
            return await interaction.response.send_message("Comando válido sólo en el servidor de reproducción.", ephemeral=True)
        hist = audio_history.get(gid) or []
        if not hist:
            return await interaction.response.send_message("No hay historial.", ephemeral=True)
        prev = hist.pop()
        audio_queues.setdefault(gid, [])
        audio_queues[gid].insert(0, {"web_url": prev.get('web_url'), "title": prev.get('title'), "text_channel": interaction.channel_id})
        voice = interaction.guild.voice_client
        if voice and (voice.is_playing() or voice.is_paused()):
            voice.stop()
        await interaction.response.send_message(f"⏮️ Reproduciendo anterior: {prev.get('title')}", ephemeral=True)

    @discord.ui.button(label="Pausa/Reanudar", style=discord.ButtonStyle.primary, emoji="⏯️")
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = self.guild_id
        if interaction.guild is None or interaction.guild.id != gid:
            return await interaction.response.send_message("Comando válido sólo en el servidor de reproducción.", ephemeral=True)
        voice = interaction.guild.voice_client
        if not voice:
            return await interaction.response.send_message("No estoy en un canal de voz.", ephemeral=True)
        if voice.is_playing():
            voice.pause()
            await interaction.response.send_message("⏸️ Pausado.", ephemeral=True)
        elif voice.is_paused():
            voice.resume()
            await interaction.response.send_message("▶️ Reanudado.", ephemeral=True)
        else:
            await interaction.response.send_message("No hay nada reproduciéndose.", ephemeral=True)

    @discord.ui.button(label="Siguiente", style=discord.ButtonStyle.success, emoji="⏭️")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = self.guild_id
        if interaction.guild is None or interaction.guild.id != gid:
            return await interaction.response.send_message("Comando válido sólo en el servidor de reproducción.", ephemeral=True)
        voice = interaction.guild.voice_client
        if not voice:
            return await interaction.response.send_message("No estoy en un canal de voz.", ephemeral=True)
        if not audio_queues.get(gid):
            # Si no hay cola, detener
            if voice.is_playing() or voice.is_paused():
                voice.stop()
            return await interaction.response.send_message("No hay siguiente canción en la cola.", ephemeral=True)
        # detener la actual; el callback de after iniciará la siguiente
        if voice.is_playing() or voice.is_paused():
            voice.stop()
        else:
            await _play_next_for_guild(gid)
        await interaction.response.send_message("⏭️ Pasando a la siguiente pista.", ephemeral=True)

    @discord.ui.button(label="Detener", style=discord.ButtonStyle.danger, emoji="⏹️")
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = self.guild_id
        if interaction.guild is None or interaction.guild.id != gid:
            return await interaction.response.send_message("Comando válido sólo en el servidor de reproducción.", ephemeral=True)
        voice = interaction.guild.voice_client
        if voice and (voice.is_playing() or voice.is_paused()):
            voice.stop()
        # limpiar cola e historial
        if gid in audio_queues:
            audio_queues[gid].clear()
        if gid in audio_history:
            audio_history[gid].clear()
        # eliminar mensaje de control si existe
        cur = audio_sources.get(gid)
        if cur:
            msg_id = cur.get('control_msg_id')
            ch_id = cur.get('text_channel')
            if msg_id and ch_id:
                ch = bot.get_channel(int(ch_id))
                if ch:
                    try:
                        m = await ch.fetch_message(int(msg_id))
                        await m.delete()
                    except Exception:
                        pass
        await interaction.response.send_message("⏹️ Detenido y cola limpiada.", ephemeral=True)


async def _send_control_message_for(guild_id: int, title: str):
    """Envía o actualiza el mensaje de controles para la guild."""
    cur = audio_sources.get(guild_id)
    if not cur:
        return
    ch_id = cur.get('text_channel')
    if not ch_id:
        return
    ch = bot.get_channel(int(ch_id))
    if not ch:
        return
    # eliminar mensaje anterior si existe
    prev_msg_id = cur.get('control_msg_id')
    if prev_msg_id:
        try:
            prev = await ch.fetch_message(int(prev_msg_id))
            try:
                await prev.delete()
            except Exception:
                pass
        except Exception:
            pass
    view = PlayerControls(guild_id)
    try:
        msg = await ch.send(f"🎶 Now playing: {title}", view=view)
        audio_sources[guild_id]["control_msg_id"] = msg.id
    except Exception as e:
        print(f"[UI] No pude enviar mensaje de control: {e}")

YDL_OPTIONS = { # Opciones de YoutubeDL
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": False,  # Cambiado a False para ver información
    "no_warnings": False,  # Permitir warnings para debugging
    "extract_flat": False,
    "default_search": "auto",
    "source_address": "0.0.0.0",
}
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5", # Opciones de FFMPEG
    "options": "-vn -bufsize 512k", # No grabar video, buffer mejorado
}


def _buscar_audio_sync(url: str): # Busca el audio en Youtube (Modo Sync)
    print(f"\n[YT-DLP] Buscando audio para: {url}")
    with YoutubeDL(YDL_OPTIONS) as ydl: # YoutubeDL con opciones
        info = ydl.extract_info(url, download=False) # Extrae la información del video
        if "entries" in info: # Si es playlist, coge el primer ítem
            info = info["entries"][0]
        title = info.get("title", "Audio")
        stream_url = info["url"]
        duration = info.get("duration", 0)
        print(f"[YT-DLP] Título: {title}")
        print(f"[YT-DLP] Duración: {duration}s")
        print(f"[YT-DLP] URL obtenida: {stream_url[:80]}...")
        return stream_url, title # Devuelve la url y el título del audio

async def buscar_audio(url: str):
    """Wrapper async para buscar audio sin bloquear."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _buscar_audio_sync, url)

def _extraer_playlist_sync(url: str):
    """Extrae los videos de una playlist de forma sincrónica (usar en executor)."""
    print(f"\n[YT-DLP] Extrayendo playlist (modo sync): {url}")
    opts = YDL_OPTIONS.copy()
    # Queremos obtener la lista completa con sus títulos y URLs
    opts.update({"noplaylist": False, "extract_flat": False, "quiet": True, "socket_timeout": 30})
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            entries = info.get("entries", [])
            videos = []
            for entry in entries:
                web = entry.get('webpage_url') or entry.get('url') or entry.get('id')
                title = entry.get('title') or web
                if web and title:
                    videos.append({"web_url": web, "title": title})
            print(f"[YT-DLP] Encontrados {len(videos)} videos en la playlist")
            return videos
    except Exception as e:
        print(f"[YT-DLP] Error extrayendo playlist: {e}")
        raise


async def extraer_playlist(url: str):
    """Wrapper async para extraer playlist sin bloquear el event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _extraer_playlist_sync, url)


async def _play_next_for_guild(guild_id: int):
    """Reproduce la siguiente pista en la cola para la guild si existe."""
    queue = audio_queues.get(guild_id, [])
    if not queue:
        print(f"[QUEUE] No hay pistas en cola para {guild_id}")
        return False

    next_item = queue.pop(0)
    web_url = next_item.get('web_url')
    title_hint = next_item.get('title') or web_url

    guild = bot.get_guild(guild_id)
    if not guild or not guild.voice_client:
        print(f"[QUEUE] Bot no conectado en guild {guild_id}")
        return False

    voice = guild.voice_client

    # Guardar historia (limitar a 50)
    cur = audio_sources.get(guild_id)
    if cur:
        audio_history.setdefault(guild_id, []).append({"web_url": cur.get('url'), "title": cur.get('title')})
        if len(audio_history[guild_id]) > 50:
            audio_history[guild_id].pop(0)

    try:
        stream_url, title = await buscar_audio(web_url)
    except Exception as e:
        print(f"[QUEUE] Error al obtener audio para {web_url}: {e}")
        return await _play_next_for_guild(guild_id)

    try:
        try:
            source = await discord.FFmpegOpusAudio.from_probe(stream_url, executable=FFMPEG_PATH, **FFMPEG_OPTIONS)
        except Exception:
            source = discord.FFmpegPCMAudio(stream_url, executable=FFMPEG_PATH, **FFMPEG_OPTIONS)
    except Exception as e:
        print(f"[QUEUE] Error creando source: {e}")
        return await _play_next_for_guild(guild_id)

    audio_sources[guild_id] = {"source": source, "title": title, "url": stream_url, "text_channel": next_item.get('text_channel')}

    def _after(err):
        if err:
            print(f"[QUEUE] Reproducción terminada con error: {err}")
        else:
            print("[QUEUE] Pista finalizada correctamente")
        if guild_id in audio_sources:
            del audio_sources[guild_id]
        try:
            fut = asyncio.run_coroutine_threadsafe(_play_next_for_guild(guild_id), bot.loop)
            fut.result(timeout=30)
        except Exception as e:
            print(f"[QUEUE] Error al continuar cola: {e}")

    voice.play(source, after=_after)
    # Notificar en el canal de texto si se proporcionó y enviar controles
    text_channel_id = next_item.get('text_channel') or audio_sources[guild_id].get('text_channel')
    if text_channel_id:
        ch = bot.get_channel(int(text_channel_id))
        if ch:
            try:
                # enviar mensaje básico y controles de UI
                await _send_control_message_for(guild_id, title)
            except Exception:
                try:
                    asyncio.run_coroutine_threadsafe(ch.send(f"▶️ Reproduciendo: {title}"), bot.loop)
                except Exception:
                    pass
    print(f"[QUEUE] Reproduciendo ahora en {guild_id}: {title}")
    return True

@bot.event
async def on_ready():
    print(f"Bot listo como {bot.user}") # Muestra el nombre del bot
    print(f"Bot ID: {bot.user.id}")
    
    # Sincronizar comandos globalmente (puede tardar hasta 1 hora)
    try:
        synced = await bot.tree.sync() # Sincroniza los comandos slash
        print(f"Sincronizados {len(synced)} comandos globalmente")
    except Exception as e:
        print(f"Error al sincronizar comandos: {e}")

    guild_id = 1375862077020831774  # Reemplaza con el ID de tu servidor
    guild = discord.Object(id=guild_id)
    bot.tree.copy_global_to(guild=guild) # Copia los comandos globales al servidor
    synced_guild = await bot.tree.sync(guild=guild) # Sincroniza los comandos al servidor
    print(f"Sincronizados {len(synced_guild)} comandos en el servidor") # Muestra cuántos comandos se sincronizaron
    

@bot.tree.command(name="join", description="Une el bot a tu canal de voz") # Comando para unir el bot a un canal de voz
async def join(interaction: discord.Interaction): # Función para unir el bot a un canal de voz
    if interaction.user.voice is None: # Si el usuario no está en un canal de voz, devuelve un mensaje de error
        return await interaction.response.send_message("Debes estar en un canal de voz.", ephemeral=True) # Devuelve un mensaje de error
    
    # Responder primero para evitar timeoutimage.png
    await interaction.response.defer() # Diferir respuesta porque puede tardar
    
    channel = interaction.user.voice.channel # Obtiene el canal de voz del usuario
    try:
        if interaction.guild.voice_client is None: # Si el bot no está en un canal de voz, se conecta al canal de voz del usuario
            await channel.connect() # Se conecta al canal de voz del usuario
        else:
            await interaction.guild.voice_client.move_to(channel) # Se mueve al canal de voz del usuario
        await interaction.followup.send(f"Conectado a {channel}") # Se envía un mensaje de confirmación
    except Exception as e: # Si ocurre un error, se envía un mensaje de error
        await interaction.followup.send(f"Error al conectar: {e}", ephemeral=True) # Se envía un mensaje de error

@bot.tree.command(name="leave", description="Desconecta el bot del canal de voz") # Comando para desconectar el bot de un canal de voz
async def leave(interaction: discord.Interaction): # Función para desconectar el bot de un canal de voz
    if interaction.guild.voice_client:
        # Limpiar el source guardado al desconectarse
        if interaction.guild.id in audio_sources: # Si el servidor está en el diccionario de audio_sources, se elimina
            del audio_sources[interaction.guild.id] # Se elimina el servidor del diccionario de audio_sources
        # Limpiar cola e historial
        gid = interaction.guild.id
        if gid in audio_queues:
            audio_queues[gid].clear()
        if gid in audio_history:
            audio_history[gid].clear()
        await interaction.guild.voice_client.disconnect() # Se desconecta el bot del canal de voz
        await interaction.response.send_message("Desconectado.") # Se envía un mensaje de confirmación
    else: # Si el bot no está en un canal de voz, se envía un mensaje de error
        await interaction.response.send_message("No estoy en un canal de voz.", ephemeral=True) # Se envía un mensaje de error

@bot.tree.command(name="play", description="Reproduce música de YouTube") # Comando para reproducir música de YouTube
@app_commands.describe(url="URL del video de YouTube") # Describe el parámetro url
async def play(interaction: discord.Interaction, url: str): # Función para reproducir música de YouTube
    if interaction.user.voice is None: # Si el usuario no está en un canal de voz, se envía un mensaje de error
        return await interaction.response.send_message("Debes estar en un canal de voz.", ephemeral=True) # Se envía un mensaje de error
    
    await interaction.response.defer() # Diferir respuesta porque puede tardar
    
    print(f"\n[PLAY] Comando ejecutado por: {interaction.user.name}") # Muestra el nombre del usuario que ejecutó el comando
    print(f"[PLAY] URL recibida: {url}") 
    
    if interaction.guild.voice_client is None: # Si el bot no está en un canal de voz, se conecta al canal de voz del usuario
        channel = interaction.user.voice.channel # Obtiene el canal de voz del usuario
        print(f"[PLAY] Conectando al canal: {channel.name}")
        await channel.connect() # Se conecta al canal de voz del usuario

    guild_id = interaction.guild.id
    audio_queues.setdefault(guild_id, [])
    audio_history.setdefault(guild_id, [])

    voice = interaction.guild.voice_client # Obtiene el canal de voz del bot
    # Detectar si la URL es una playlist (varios entries)
    try:
        with YoutubeDL({**YDL_OPTIONS, "noplaylist": False, "quiet": True, "extract_flat": True}) as ydl:
            info_check = ydl.extract_info(url, download=False)
            if "entries" in info_check and len(info_check.get("entries", [])) > 1:
                # Es una playlist: extraer lista completa con títulos y urls
                await interaction.followup.send("⏳ Extrayendo playlist... esto puede tardar un poco.")
                videos = await extraer_playlist(url)  # Ahora es async
                if not videos:
                    raise ValueError("No encontré videos en la playlist")
                # Encolar todos
                for item in videos:
                    audio_queues[guild_id].append({"web_url": item.get('web_url'), "title": item.get('title'), "text_channel": interaction.channel_id})
                # Si ya está reproduciendo, solo confirmamos encolado
                if voice and (voice.is_playing() or voice.is_paused()):
                    await interaction.followup.send(f"✅ Encolada playlist ({len(videos)} canciones).")
                    return
                # Si no está reproduciendo, iniciar la primera de la cola
                started = await _play_next_for_guild(guild_id)
                if started:
                    await interaction.followup.send(f"✅ Encolada playlist ({len(videos)} canciones). Reproduciendo la primera ahora.")
                else:
                    await interaction.followup.send(f"✅ Encolada playlist ({len(videos)} canciones), no pude iniciar reproducción.", ephemeral=True)
                return
    except Exception as e:
        # No es una playlist o falla la detección: continuar como URL individual
        pass
    # Si ya está reproduciendo, encolamos la URL
    if voice.is_playing() or voice.is_paused():
        try:
            with YoutubeDL({**YDL_OPTIONS, "noplaylist": True, "quiet": True}) as ydl:
                info = ydl.extract_info(url, download=False)
                if "entries" in info:
                    info = info["entries"][0]
                title = info.get('title', url)
        except Exception:
            title = url
        audio_queues[guild_id].append({"web_url": url, "title": title, "text_channel": interaction.channel_id})
        await interaction.followup.send(f"Encolado: {title}")
        print(f"[PLAY] Encolado en {guild_id}: {title}")
        return

    try:
        print("[PLAY] Obteniendo información del audio...")
        stream_url, title = await buscar_audio(url) # Busca el audio en Youtube
    except Exception as e: # Si ocurre un error, se envía un mensaje de error
        print(f"[PLAY] ERROR al obtener audio: {e}")
        return await interaction.followup.send(f"No pude obtener el audio: {e}", ephemeral=True)

    try:
        print("[FFMPEG] Iniciando fuente de audio...") # Muestra un mensaje de que se inicia la fuente de audio
        print(f"[FFMPEG] Ejecutable: {FFMPEG_PATH}")
        print(f"[FFMPEG] Opciones: {FFMPEG_OPTIONS}") # Muestra las opciones de FFMPEG
        
        # Intentar primero con from_probe, si falla usar FFmpegPCMAudio
        try:
            source = await discord.FFmpegOpusAudio.from_probe( # Se crea la fuente de audio con FFmpegOpusAudio.from_probe
                stream_url, 
                executable=FFMPEG_PATH, # Ruta del ejecutable de FFMPEG
                **FFMPEG_OPTIONS
            )
            print("[FFMPEG] Fuente creada con FFmpegOpusAudio.from_probe") # Muestra un mensaje de que se creó la fuente de audio con FFmpegOpusAudio.from_probe
        except Exception as probe_error:
            print(f"[FFMPEG] from_probe falló: {probe_error}") # Muestra un mensaje de que from_probe falló
            print("[FFMPEG] Intentando con FFmpegPCMAudio como alternativa...")
            source = discord.FFmpegPCMAudio( # Se crea la fuente de audio con FFmpegPCMAudio
                stream_url,
                executable=FFMPEG_PATH, # Ruta del ejecutable de FFMPEG
                **FFMPEG_OPTIONS
            )
            print("[FFMPEG] Fuente creada con FFmpegPCMAudio") # Muestra un mensaje de que se creó la fuente de audio con FFmpegPCMAudio
        
        print(f"[PLAY] Iniciando reproducción de: {title}") # Muestra el título de la canción que se va a reproducir
        
        # Guardar el source en el diccionario para poder pausar/reanudar y el canal de texto
        audio_sources[guild_id] = { # Se guarda el source en el diccionario de audio_sources
            "source": source,
            "title": title, # Se guarda el título de la canción
            "url": stream_url, # Se guarda la url de la canción
            "text_channel": interaction.channel_id,
        }

        def after_playing(error): # Función para después de la reproducción
            if error:
                print(f"\n[PLAY] Reproducción finalizada con error: {error}") # Muestra un mensaje de que la reproducción finalizó con error
            else:
                print("\n[PLAY] Reproducción terminada correctamente") # Muestra un mensaje de que la reproducción terminó correctamente
            # Limpiar el source cuando termine
            if guild_id in audio_sources: # Si el servidor está en el diccionario de audio_sources, se elimina
                del audio_sources[guild_id] # Se elimina el servidor del diccionario de audio_sources
            # Intentar reproducir siguiente de la cola
            try:
                fut = asyncio.run_coroutine_threadsafe(_play_next_for_guild(guild_id), bot.loop)
                fut.result(timeout=30)
            except Exception as e:
                print(f"[PLAY] Error al reproducir siguiente: {e}")
        
        voice.play(source, after=after_playing) # Se reproduce la canción
        # enviar mensaje con controles
        try:
            await _send_control_message_for(guild_id, title)
            await interaction.followup.send(f"Reproduciendo: {title}")
        except Exception:
            await interaction.followup.send(f"Reproduciendo: {title}") # Fallback: solo texto
        print(f"[PLAY] Reproducción iniciada exitosamente: {title}") # Muestra un mensaje de que la reproducción inició correctamente
        
    except Exception as e: # Si ocurre un error, se envía un mensaje de error
        print(f"[PLAY] ERROR al reproducir: {e}") # Muestra un mensaje de que la reproducción finalizó con error
        await interaction.followup.send(f"Error al reproducir: {e}", ephemeral=True) # Se envía un mensaje de error

@bot.tree.command(name="pause", description="Pausa la reproducción") # Comando para pausar la reproducción
async def pause(interaction: discord.Interaction): # Función para pausar la reproducción
    voice = interaction.guild.voice_client # Obtiene el canal de voz del bot
    if not voice:
        return await interaction.response.send_message("No estoy en un canal de voz.", ephemeral=True) # Se envía un mensaje de error
    
    if voice.is_playing(): # Si el bot está reproduciendo, se pausa
        print(f"[PAUSE] Pausando reproducción en servidor {interaction.guild.id}") # Muestra el ID del servidor en el que se está pausando la reproducción
        voice.pause()
        await interaction.response.send_message("⏸️ Pausado.") # Se envía un mensaje de confirmación
    elif voice.is_paused():
        await interaction.response.send_message("Ya está pausado.", ephemeral=True) # Se envía un mensaje de error
    else:
        await interaction.response.send_message("No hay nada reproduciéndose.", ephemeral=True) # Se envía un mensaje de error

@bot.tree.command(name="resume", description="Reanuda la reproducción") # Comando para reanudar la reproducción
async def resume(interaction: discord.Interaction): # Función para reanudar la reproducción
    voice = interaction.guild.voice_client
    if not voice:
        return await interaction.response.send_message("No estoy en un canal de voz.", ephemeral=True) # Se envía un mensaje de error
    
    if voice.is_paused():
        print(f"[RESUME] Reanudando reproducción en servidor {interaction.guild.id}") # Muestra el ID del servidor en el que se está reanudando la reproducción
        voice.resume() # Se reanuda la reproducción
        await interaction.response.send_message("▶️ Reanudado.") # Se envía un mensaje de confirmación
    elif voice.is_playing():
        await interaction.response.send_message("Ya está reproduciéndose.", ephemeral=True)
    else:
        # Si no está pausado ni reproduciendo, intentar reanudar desde el source guardado
        if interaction.guild.id in audio_sources:
            saved_data = audio_sources[interaction.guild.id]
            print(f"[RESUME] No hay source activo, pero hay uno guardado. Reiniciando...") # Muestra un mensaje de que no hay source activo, pero hay uno guardado
            try:
                # Recrear el source desde la URL guardada
                try:
                    source = await discord.FFmpegOpusAudio.from_probe( # Se crea la fuente de audio con FFmpegOpusAudio.from_probe
                        saved_data["url"], 
                        executable=FFMPEG_PATH, # Ruta del ejecutable de FFMPEG
                        **FFMPEG_OPTIONS
                    )
                except:
                    source = discord.FFmpegPCMAudio( # Se crea la fuente de audio con FFmpegPCMAudio
                        saved_data["url"],
                        executable=FFMPEG_PATH, # Ruta del ejecutable de FFMPEG
                        **FFMPEG_OPTIONS
                    )
                
                audio_sources[interaction.guild.id]["source"] = source # Se guarda el source en el diccionario de audio_sources
                voice.play(source, after=lambda e: print(f"\n[PLAY] Reproducción finalizada: {e}" if e else "\n[PLAY] Reproducción terminada correctamente"))
                await interaction.response.send_message(f"▶️ Reanudando: {saved_data['title']}") # Se envía un mensaje de confirmación
            except Exception as e:
                print(f"[RESUME] ERROR al reanudar: {e}") # Muestra un mensaje de que la reanudación finalizó con error
                await interaction.response.send_message(f"Error al reanudar: {e}", ephemeral=True) # Se envía un mensaje de error
        else:
            await interaction.response.send_message("No hay nada pausado ni guardado para reanudar.", ephemeral=True) # Se envía un mensaje de error

@bot.tree.command(name="stop", description="Detiene la reproducción") # Comando para detener la reproducción
async def stop(interaction: discord.Interaction): # Función para detener la reproducción
    voice = interaction.guild.voice_client # Obtiene el canal de voz del bot
    if not voice: 
        return await interaction.response.send_message("No estoy en un canal de voz.", ephemeral=True) # Se envía un mensaje de error
    
    if voice.is_playing() or voice.is_paused(): # Si el bot está reproduciendo o pausado, se detiene
        print(f"[STOP] Deteniendo reproducción en servidor {interaction.guild.id}") # Muestra el ID  del servidor en el que se está deteniendo la reproducción
        voice.stop() # Se detiene la reproducción
        # Limpiar el source guardado
        if interaction.guild.id in audio_sources: # Si el servidor está en el diccionario de audio_sources, se elimina
            del audio_sources[interaction.guild.id] # Se elimina el servidor del diccionario de audio_sources
        await interaction.response.send_message("⏹️ Detenido.") # Se envía un mensaje de confirmación
    else: # Si el bot no está reproduciendo ni pausado, se envía un mensaje de error
        await interaction.response.send_message("No hay nada reproduciéndose.", ephemeral=True) # Se envía un mensaje de error
 
@bot.tree.command(name="siguiente", description="Pasa a la siguiente canción en la cola")
async def siguiente(interaction: discord.Interaction):
    if interaction.guild is None:
        return await interaction.response.send_message("Comando disponible solo en servidores.", ephemeral=True)
    voice = interaction.guild.voice_client
    if not voice:
        return await interaction.response.send_message("No estoy en un canal de voz.", ephemeral=True)
    gid = interaction.guild.id
    if not audio_queues.get(gid):
        # No hay cola: detener y limpiar
        if voice.is_playing() or voice.is_paused():
            voice.stop()
        return await interaction.response.send_message("No hay siguiente canción en la cola.", ephemeral=True)
    # Detener la actual (after callback lanzará la siguiente)
    if voice.is_playing() or voice.is_paused():
        voice.stop()
    # Intentar iniciar la siguiente inmediatamente
    ok = await _play_next_for_guild(gid)
    if ok:
        await interaction.response.send_message("⏭️ Pasando a la siguiente pista.")
    else:
        await interaction.response.send_message("No pude iniciar la siguiente pista.", ephemeral=True)


@bot.tree.command(name="anterior", description="Reproduce la canción anterior (si existe historial)")
async def anterior(interaction: discord.Interaction):
    if interaction.guild is None:
        return await interaction.response.send_message("Comando disponible solo en servidores.", ephemeral=True)
    gid = interaction.guild.id
    hist = audio_history.get(gid) or []
    if not hist:
        return await interaction.response.send_message("No hay historial de canciones.", ephemeral=True)
    prev = hist.pop()  # obtenemos la última
    # Ponerla al frente de la cola y forzar reproducción
    audio_queues.setdefault(gid, [])
    audio_queues[gid].insert(0, {"web_url": prev.get('web_url'), "title": prev.get('title'), "text_channel": interaction.channel_id})
    voice = interaction.guild.voice_client
    if voice and (voice.is_playing() or voice.is_paused()):
        voice.stop()
    ok = await _play_next_for_guild(gid)
    if ok:
        await interaction.response.send_message(f"⏮️ Reproduciendo anterior: {prev.get('title')}")
    else:
        await interaction.response.send_message("No pude reproducir la pista anterior.", ephemeral=True)


@bot.tree.command(name="np", description="Muestra la canción que se está reproduciendo ahora")
async def now_playing(interaction: discord.Interaction):
    if interaction.guild is None:
        return await interaction.response.send_message("Comando disponible solo en servidores.", ephemeral=True)
    gid = interaction.guild.id
    cur = audio_sources.get(gid)
    if cur:
        title = cur.get('title')
        return await interaction.response.send_message(f"🎶 Ahora reproduciendo: {title}")
    else:
        return await interaction.response.send_message("No hay ninguna pista reproduciéndose.", ephemeral=True)


@bot.tree.command(name="playlist", description="Encola y reproduce una playlist de YouTube (URL de playlist)")
@app_commands.describe(url="URL de la playlist de YouTube")
async def playlist(interaction: discord.Interaction, url: str):
    if interaction.user.voice is None:
        return await interaction.response.send_message("Debes estar en un canal de voz.", ephemeral=True)
    await interaction.response.defer()
    gid = interaction.guild.id
    audio_queues.setdefault(gid, [])
    
    # Notificar que se está extrayendo
    try:
        await interaction.followup.send("⏳ Extrayendo playlist... esto puede tardar un poco.")
    except Exception:
        pass
    
    try:
        videos = await extraer_playlist(url)  # Ahora es async y no bloquea
    except Exception as e:
        print(f"[PLAYLIST] Error extrayendo: {e}")
        return await interaction.followup.send(f"No pude extraer la playlist: {e}", ephemeral=True)
    
    if not videos:
        return await interaction.followup.send("No encontré videos en la playlist.", ephemeral=True)
    
    # Encolar todos (los títulos ya vienen de extraer_playlist)
    count = 0
    for item in videos:
        web = item.get('web_url') if isinstance(item, dict) else item
        title = item.get('title') if isinstance(item, dict) else web
        if web:
            audio_queues[gid].append({"web_url": web, "title": title, "text_channel": interaction.channel_id})
            count += 1
    
    print(f"[PLAYLIST] Encoladas {count} canciones en {gid}")
    
    # Si no se está reproduciendo, iniciar la primera
    voice = interaction.guild.voice_client
    if not voice or not (voice.is_playing() or voice.is_paused()):
        started = await _play_next_for_guild(gid)
        if started:
            await interaction.followup.send(f"✅ Encolada playlist ({count} canciones). Reproduciendo la primera ahora.")
        else:
            await interaction.followup.send(f"✅ Encolada playlist ({count} canciones), pero no pude iniciar reproducción.", ephemeral=True)
    else:
        await interaction.followup.send(f"✅ Encolada playlist ({count} canciones).")
bot.run(TOKEN) # Se ejecuta el bot