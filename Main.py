import os
import time
import asyncio
import discord
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv
from yt_dlp import YoutubeDL
import logging
import logging
import database as db
import random
import requests
import re
from datetime import datetime 


load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN") # Token del bot
ADMIN_ID = os.getenv("ADMIN_ID") # ID del administrador (o IDs separados por comas)
intents = discord.Intents.default() # Intents del bot
intents.message_content = True
intents.members = True # Necesario para buscar miembros por nombre

bot = commands.Bot(command_prefix="!", intents=intents)

# Diccionario para guardar el source de audio por servidor
# Esto permite pausar y reanudar sin perder el source
audio_sources = {}

music_queues = {}

# Configurar logging a consola y archivo
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("discord.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("music_bot")

YDL_OPTIONS = { # Opciones de YoutubeDL
    "format": "bestaudio/best", # Mejor calidad disponible (sin límite)
    "noplaylist": True,
    "quiet": True, 
    "no_warnings": True,
    "extract_flat": False,
    "default_search": "auto",
    "source_address": "0.0.0.0",
    "http_chunk_size": 10485760, # 10MB chunk para evitar throttling
    "force_generic_extractor": False,
}
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -reconnect_at_eof 1",
    "options": "-vn"
}
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")

# Configuración Spotify (Opcional)
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

spotify = None
if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    try:
        auth_manager = SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET)
        spotify = spotipy.Spotify(auth_manager=auth_manager)
        print("[SPOTIFY] Cliente inicializado correctamente.")
    except Exception as e:
        print(f"[SPOTIFY] Error al inicializar: {e}")


##---------------------FUNCIONES---------------------##

def is_spotify_url(text: str) -> bool:
    return "open.spotify.com" in text or text.startswith("spotify:")

def get_spotify_queries(url: str):
    """Devuelve lista de búsquedas (texto) para YouTube a partir de una URL de Spotify."""
    if spotify is None:
        raise RuntimeError(
            "Spotify no está configurado. Revisa SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET en .env"
        )

    # Canción individual
    if "track" in url:
        track = spotify.track(url)
        name = track["name"]
        artists = track.get("artists", [])
        artist = artists[0]["name"] if artists else ""
        return [f"{name} {artist}".strip()]

    # Playlist completa
    if "playlist" in url:
        queries = []
        results = spotify.playlist_items(url, additional_types=["track"])
        while True:
            for item in results["items"]:
                track = item.get("track")
                if not track:
                    continue
                name = track["name"]
                artists = track.get("artists", [])
                artist = artists[0]["name"] if artists else ""
                queries.append(f"{name} {artist}".strip())

            # Paginación de Spotify
            if results.get("next"):
                results = spotify.next(results)
            else:
                break
        return queries
    
    # Album
    if "album" in url:
        queries = []
        results = spotify.album_tracks(url)
        while True:
            for item in results["items"]: # Album tracks are simpler
                name = item["name"]
                artists = item.get("artists", [])
                artist = artists[0]["name"] if artists else ""
                queries.append(f"{name} {artist}".strip())
                
            if results.get("next"):
                results = spotify.next(results)
            else:
                break
        return queries

    raise ValueError("Solo se soportan URLs de track, playlist o álbum de Spotify.")



def buscar_audio(url: str): # Busca el audio en Youtube
    print(f"\n[YT-DLP] Buscando audio para: {url}")
    
    # 🟢 SOPORTE SPOTIFY (Scraping básico)
    if "open.spotify.com" in url and "track" in url:
        try:
            print("[SPOTIFY] Enlace detectado. Intentando extraer info...")
            # Headers para evitar bloqueos
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
            r = requests.get(url, headers=headers)
            
            if r.status_code == 200:
                # Buscamos og:title (Título - Artista)
                # Suele ser: <meta property="og:title" content="Canción" />
                # y <meta property="og:description" content="Artista · Song · 2023" />
                
                title_match = re.search(r'<meta property="og:title" content="(.*?)"', r.text)
                desc_match = re.search(r'<meta property="og:description" content="(.*?)"', r.text)
                
                if title_match:
                    sp_title = title_match.group(1)
                    sp_artist = ""
                    if desc_match:
                        # La descripción suele ser "Artist · Song · Year"
                        sp_artist = desc_match.group(1).split("·")[0].strip()
                    
                    search_query = f"{sp_title} {sp_artist} audio"
                    print(f"[SPOTIFY] Encontrado: {sp_title} - {sp_artist}")
                    print(f"[SPOTIFY] Buscando en YouTube: {search_query}")
                    url = f"ytsearch:{search_query}" # Cambiamos la URL a búsqueda de YT
        except Exception as e:
            print(f"[SPOTIFY] Error al procesar enlace: {e}")

    with YoutubeDL(YDL_OPTIONS) as ydl: # YoutubeDL con opciones
        info = ydl.extract_info(url, download=False) # Extrae la información del video
        if "entries" in info: # Si es playlist (o resultado de búsqueda), coge el primer ítem
            info = info["entries"][0]
        title = info.get("title", "Audio")
        stream_url = info["url"]
        webpage_url = info.get("webpage_url", url) # URL Real para el link
        duration = info.get("duration", 0)
        print(f"[YT-DLP] Título: {title}")
        print(f"[YT-DLP] Duración: {duration}s")
        print(f"[YT-DLP] URL obtenida: {stream_url[:80]}...")
        thumbnail = info.get("thumbnail") # Obtener miniatura
        return stream_url, title, duration, thumbnail, webpage_url

def buscar_playlist(url: str):
    """Busca una playlist en YouTube y devuelve lista de videos (flat)."""
    print(f"\n[YT-DLP] Buscando playlist: {url}")
    
    opts = YDL_OPTIONS.copy()
    opts['extract_flat'] = True # Solo sacar info básica, no stream
    opts['noplaylist'] = False # Permitir playlists
    
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if "entries" not in info:
            return None, "No se encontraron canciones o no es una playlist."
            
        tracks = []
        for entry in info["entries"]:
            # A veces extract_flat devuelve entradas que no son videos
            if entry.get("ie_key") == "Youtube":
               tracks.append({
                   "title": entry.get("title", "Audio"),
                   "webpage_url": entry.get("url"),
                   "duration": entry.get("duration", 0) # Puede ser None
               })
        
        return tracks, info.get("title", "Playlist")


def create_progress_bar(elapsed, total, length=15):
    """Crea una barra de progreso visual [==🔘---]"""
    if total == 0: return "�" + "─" * length
    
    percent = min(1, max(0, elapsed / total))
    progress = int(length * percent)
    
    # Estilo minimalista SOLIDO
    bar = "▬" * progress + "🔘" + "─" * (length - progress)
    
    # Formatear tiempo
    def fmt(s):
        m, s = divmod(int(s), 60)
        h, m = divmod(m, 60)
        if h > 0: return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"
        
    return f"`{bar}` **{fmt(elapsed)} / {fmt(total)}**"

def create_minimal_embed(title, url, duration, elapsed, thumbnail, requester=None, channel_name=None):
    """Genera un Embed estilo Rythm (Minimalista)"""
    
    # 1. Calcular barra
    length = 20
    if duration > 0:
        percent = min(1, max(0, elapsed / duration))
        progress = int(length * percent)
    else:
        progress = 0
        
    bar = "▬" * progress + "🔘" + "─" * (length - progress)
    
    # 2. Formatear tiempo
    def fmt(s):
        m, s = divmod(int(s), 60)
        h, m = divmod(m, 60)
        if h > 0: return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    time_str = f"`{fmt(elapsed)} / {fmt(duration)}`"

    # 3. Construir Embed
    embed = discord.Embed(color=0x2b2d31)
    
    # Author = "Now Playing"
    embed.set_author(name="Tune Flow", icon_url="https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExYmVmNDQ4d210cjNxczNleXJ4ODI2bDJ1OGMwdHE5YnhmdWVmdmVyZyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/yZ7Xya4covzN1WhOAa/giphy.gif")
    
    # Description: Title + Meta + Bar
    desc = f"**[{title}]({url})**\n"
    
    # Detectar Plataforma
    platform = "🔗 Otro"
    if "spotify" in url: platform = "💚 Spotify"
    elif "youtu" in url: platform = "🟥 YouTube"
    elif "soundcloud" in url: platform = "🧡 SoundCloud"
    
    meta = []
    meta.append(platform)
    if requester: meta.append(f"👤 {requester}")
    if channel_name: meta.append(f"🔊 {channel_name}")
    
    if meta:
        desc += " | ".join(meta) + "\n"
        
    desc += f"\n{time_str}\n{bar}"
    
    embed.description = desc

    embed.description = desc

    # Carátula GRANDE (ocupa todo el ancho del embed)
    if not thumbnail:
        thumbnail = "https://cdn-icons-png.flaticon.com/512/1384/1384060.png" # Icono Youtube genérico funcional
        
    embed.set_image(url=thumbnail)  # Cambiado de set_thumbnail a set_image para mayor impacto visual
    
    # Footer con metadata mejorado
    footer_parts = []
    if requester:
        footer_parts.append(f"👤 {requester}")
    if channel_name:
        footer_parts.append(f"🔊 {channel_name}")
    footer_parts.append("✨ Autoplay: ON")
    
    embed.set_footer(text=" • ".join(footer_parts))
    
    return embed


def get_today_history(history_list):
    """Filtra el historial para mostrar solo las canciones de hoy"""
    today = datetime.now().date()
    return [item for item in history_list if item.get("timestamp") and item["timestamp"].date() == today]

##---------------------FIN DE LAS FUNCIONES---------------------##

async def update_message_task(message, start_time, duration, title, voice_client):
    """
    Tarea en segundo plano que actualiza la barra de progreso del mensaje cada segundo.
    """
    try:
        while True:
            await asyncio.sleep(1) # Actualizar cada segundo
            
            # Condiciones de parada
            if not voice_client.is_connected(): break
            if not voice_client.is_playing() and not voice_client.is_paused(): break # Ya no suena
            
            # Calcular nuevo progreso
            # Elapsed = (now - start) + offset
            elapsed = (time.time() - start_time) + audio_sources.get(voice_client.guild.id, {}).get("offset", 0)
            
            if elapsed > duration: elapsed = duration 
            
            # Recuperar info para el embed
            src_info = audio_sources.get(voice_client.guild.id, {})
            url = src_info.get("url", "")
            thumb = src_info.get("thumbnail")

            # Recrear embed minimalista
            chn_name = voice_client.channel.name if voice_client.channel else "Voz"
            embed = create_minimal_embed(title, url, duration, elapsed, thumb, channel_name=chn_name)
            
            try:
                await message.edit(embed=embed)
            except discord.NotFound:
                break # Mensaje borrado
            except Exception as e:
                print(f"[UPDATER] Error al editar mensaje: {e}")
                break
                
            if elapsed >= duration: break
            
    except Exception as e:
        print(f"[UPDATER] Error fatal en task: {e}")

@tasks.loop(seconds=60) # Ejecutar cada 60 segundos
async def clean_chat_task():
    """Tarea que limpia mensajes antiguos del bot en los canales de música."""
    try:
        # Iterar sobre las colas activas para saber qué canales limpiar
        # Copiamos keys para evitar error si el dict cambia
        for guild_id in list(music_queues.keys()):
            queue = music_queues[guild_id]
            channel = queue.get("channel")
            if not channel: continue
            
            # Identificar el mensaje del reproductor activo para NO borrarlo
            active_msg_id = None
            if guild_id in audio_sources and "message" in audio_sources[guild_id]:
                try:
                    active_msg_id = audio_sources[guild_id]["message"].id
                except: pass
            
            # Función para identificar qué borrar
            def is_dirty(m):
                # Borrar mensajes del BOT que NO sean el player activo
                if m.author.id == bot.user.id:
                    if m.id != active_msg_id:
                        return True
                return False

            # Purge (Solo miramos los últimos 50 mensajes para no saturar API)
            try:
                # Usamos bulk=True por defecto
                deleted = await channel.purge(limit=50, check=is_dirty)
                if deleted:
                    print(f"[AUTO-CLEAN] Borrados {len(deleted)} mensajes en {channel.guild.name} - #{channel.name}")
            except Exception as e:
                print(f"[AUTO-CLEAN] Error en purge: {e}")
                
    except Exception as e:
        print(f"[AUTO-CLEAN] Error general: {e}")

@tasks.loop(hours=24)  # Ejecutar cada 24 horas
async def daily_history_cleanup():
    """Limpia el historial eliminando canciones de días anteriores."""
    try:
        today = datetime.now().date()
        cleaned_guilds = 0
        
        for guild_id in list(music_queues.keys()):
            if "history" in music_queues[guild_id]:
                old_count = len(music_queues[guild_id]["history"])
                # Filtrar solo canciones de hoy
                music_queues[guild_id]["history"] = [
                    item for item in music_queues[guild_id]["history"]
                    if item.get("timestamp") and item["timestamp"].date() == today
                ]
                new_count = len(music_queues[guild_id]["history"])
                
                if old_count != new_count:
                    cleaned_guilds += 1
                    print(f"[HISTORY-CLEANUP] Guild {guild_id}: Limpiadas {old_count - new_count} canciones antiguas")
        
        if cleaned_guilds > 0:
            print(f"[HISTORY-CLEANUP] Limpieza diaria completada. {cleaned_guilds} servidores actualizados.")
    except Exception as e:
        print(f"[HISTORY-CLEANUP] Error en limpieza diaria: {e}")

disconnect_tasks = {} # Tareas de desconexión por guild

async def disconnect_timer(guild, timeout=300): # timeout en segundos
    """Espera timeout segundos y desconecta si sigue inactivo."""
    print(f"[AUTO-DISCONNECT] Iniciando timer de {timeout}s para {guild.name}")
    await asyncio.sleep(timeout)
    
    # Verificar si seguimos teniendo que desconectar
    voice = guild.voice_client
    if not voice or not voice.is_connected(): return # Ya se fue
    
    # 1. Chequeo Miembros (Bot solo)
    if len(voice.channel.members) == 1:
        await voice.disconnect()
        await update_bot_status(None)  # Limpiar estado
        if guild.id in music_queues:
            channel = music_queues[guild.id]["channel"]
            await channel.send("🔌 Me desconecté por inactividad (me dejasteis solo).")
            del music_queues[guild.id]
        return

    # 2. Chequeo Cola (No suena nada)
    if not voice.is_playing() and not voice.is_paused():
        # Doble check de cola
        q = music_queues.get(guild.id)
        if not q or q["index"] >= len(q["tracks"]):
             await voice.disconnect()
             await update_bot_status(None)  # Limpiar estado
             if q:
                 channel = q["channel"]
                 await channel.send("🔌 Me desconecté tras 5 minutos sin música.")
                 del music_queues[guild.id]

async def check_disconnect(guild):
    """Evalúa si hay que iniciar el timer de desconexión."""
    # Cancelar timer previo si existe (porque ha pasado algo: entró gente o se puso música)
    if guild.id in disconnect_tasks:
        disconnect_tasks[guild.id].cancel()
        del disconnect_tasks[guild.id]
        
    voice = guild.voice_client
    if not voice: return
    
    should_disconnect = False
    # Caso A: Solo en el canal
    if len(voice.channel.members) == 1: 
        should_disconnect = True
    
    # Caso B: No suena nada Y cola vacía
    if not voice.is_playing() and not voice.is_paused():
        q = music_queues.get(guild.id)
        if not q or q["index"] >= len(q["tracks"]):
            should_disconnect = True
            
    if should_disconnect:
        disconnect_tasks[guild.id] = bot.loop.create_task(disconnect_timer(guild))

@bot.event
async def on_voice_state_update(member, before, after):
    # Si alguien entra o sale del canal del bot
    if member.bot: return 
    
    # Buscar si el bot está en algún canal afectado
    # Opción A: el bot es member (el bot se movió) -> Check
    # Opción B: alguien se unió al canal del bot -> Cancelar timer
    # Opción C: alguien se fue del canal del bot -> Check (si se queda solo)
    
    guild = member.guild
    voice = guild.voice_client
    if not voice: return
    
    if before.channel == voice.channel or after.channel == voice.channel:
        # Hubo movimiento en el canal del bot
        await check_disconnect(guild)

async def cleanup_previous_message(guild_id):
    """Elimina el mensaje de reproducción anterior y cancela su tarea."""
    if guild_id not in audio_sources: 
        print(f"[CLEANUP] Guild {guild_id} no encontrada en audio_sources.")
        return
    
    info = audio_sources[guild_id]
    
    # Cancelar tarea
    if "task" in info:
        info["task"].cancel()
        print("[CLEANUP] Tarea cancelada.")
        
    # Borrar mensaje
    if "message" in info:
        try:
            print(f"[CLEANUP] Intentando borrar mensaje ID: {info['message'].id}")
            await info["message"].delete()
            print("[CLEANUP] Mensaje borrado correctamente.")
        except discord.NotFound:
            print("[CLEANUP] Mensaje no encontrado (ya borrado).")
        except Exception as e:
            print(f"[CLEANUP] Error borrando mensaje: {e}")
    else:
        print("[CLEANUP] No se encontró clave 'message' en audio_sources.")
            
    # Limpiar referencias
    info.pop("task", None)
    info.pop("message", None)

async def update_bot_status(title: str = None):
    """Actualiza el estado del bot (Rich Presence)."""
    try:
        if title:
            # Truncar si es muy largo (Discord tiene límite de 128 caracteres)
            display_title = title[:120] if len(title) > 120 else title
            await bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.listening,
                    name=display_title
                )
            )
            print(f"[STATUS] Actualizado a: {display_title}")
        else:
            # Limpiar estado (idle)
            await bot.change_presence(activity=None)
            print("[STATUS] Estado limpiado.")
    except Exception as e:
        print(f"[STATUS] Error actualizando estado: {e}")
    

@bot.tree.command(name="play", description="Reproduce música de YouTube")
@app_commands.describe(url="URL del video de YouTube")
async def play(interaction: discord.Interaction, url: str):
    if interaction.user.voice is None:
        return await interaction.response.send_message("Debes estar en un canal de voz.", ephemeral=True)

    await interaction.response.defer()

    print(f"\n[PLAY] Comando ejecutado por: {interaction.user.name}")
    print(f"[PLAY] URL recibida: {url}")
    logger.info("[PLAY] Comando por %s - URL: %s", interaction.user.name, url)

    # Conectar al canal de voz si no está conectado
    if interaction.guild.voice_client is None:
        channel = interaction.user.voice.channel
        print(f"[PLAY] Conectando al canal: {channel.name}")
        await channel.connect()

    voice = interaction.guild.voice_client
    # ELIMINADO: No paramos la música aquí, dejaremos que la lógica de cola lo maneje
    
    # Asegurar que existe la cola antes de nada
    if interaction.guild.id not in music_queues:
        music_queues[interaction.guild.id] = {
            "tracks": [], "index": 0, "channel": interaction.channel, "loop": False, "history": []
        }
    music_queues[interaction.guild.id]["channel"] = interaction.channel
    queue = music_queues[interaction.guild.id]

    # 🟢 CHECK SPOTIFY
    if is_spotify_url(url):
        try:
            print("[PLAY] Detectada URL de Spotify...")
            queries = get_spotify_queries(url)
            
            if not queries:
                 return await interaction.followup.send("No se encontraron canciones válidas en ese enlace de Spotify.", ephemeral=True)
            
            # Si es solo 1 (track)
            if len(queries) == 1:
                query = queries[0]
                url = f"ytsearch:{query}" # Convertimos y seguimos abajo
                print(f"[SPOTIFY] Convertido a: {url}")
            else:
            # Spotify Playlist Message
                msg_txt = f"🎶 Añadiendo **{len(queries)}** canciones de Spotify a la cola..."
                sp_msg = await interaction.followup.send(msg_txt)
                try:
                    await sp_msg.delete(delay=1)
                except: pass
                
                for q in queries:
                    track_obj = {
                        "title": q, 
                        "webpage_url": f"ytsearch:{q}", 
                        "duration": 0, 
                        "thumbnail": None
                    }
                    queue["tracks"].append(track_obj)
                
                # Iniciar reproducción si está silencio
                if not voice.is_playing() and not voice.is_paused():
                    if len(queue["tracks"]) == len(queries): queue["index"] = 0
                    
                    try:
                        first_track = queue["tracks"][queue["index"]]
                        real_title, real_duration, thumbnail = await play_track_in_guild(interaction.guild, first_track)
                        
                        await cleanup_previous_message(interaction.guild.id)
                        progress_bar = create_progress_bar(0, real_duration)
                        embed = discord.Embed(title="🎵 Reproduciendo Spotify", description=f"**{real_title}**\n\n{progress_bar}", color=discord.Color.green())
                        if thumbnail: embed.set_thumbnail(url=thumbnail)
                        
                        msg = await interaction.followup.send(embed=embed, view=PlayerView(interaction.guild.id))
                        
                        if real_duration > 0:
                            task = bot.loop.create_task(update_message_task(msg, time.time(), real_duration, real_title, voice))
                            audio_sources[interaction.guild.id] = audio_sources.get(interaction.guild.id, {})
                            audio_sources[interaction.guild.id]["message"] = msg
                            audio_sources[interaction.guild.id]["start_time"] = time.time()
                            audio_sources[interaction.guild.id]["task"] = task
                    except Exception as e:
                       print(f"Error arrancando playlist Spotify: {e}")
                return # Salir, ya manejamos todo
                
        except RuntimeError as re_err:
            return await interaction.followup.send(f"⚠️ {re_err}", ephemeral=True)
        except Exception as e:
            print(f"Error Spotify: {e}")
            return await interaction.followup.send(f"Error procesando Spotify: {e}", ephemeral=True)

    # Obtener info del audio (YOUTUBE / SEARCH)
    try:
        print("[PLAY] Obteniendo información del audio...")
        logger.info("[PLAY] Buscando stream...")
        stream_url, title, duration, thumbnail, webpage_url = buscar_audio(url)
    except Exception as e:
        print(f"[PLAY] ERROR al obtener audio: {e}")
        logger.error("[PLAY] No pude obtener el audio: %s", e)
        return await interaction.followup.send(f"No pude obtener el audio: {e}", ephemeral=True)

    try:
        print(f"[PLAY] Información obtenida: {title}")
        logger.info("Reproduciendo/Encolando: %s", title)

        # (La cola ya está inicializada arriba, no hace falta checkear music_queues again)

        queue = music_queues[interaction.guild.id]

        
        # Opcional: Bloquear playlists de YT en /play (sugerir /playlist)
        if "list=" in url and not "watch?v=" in url and not "ytsearch:" in url:
             return await interaction.followup.send("⚠️ Para playlists de YouTube usa `/playlist <url>`. `/play` es para canciones sueltas.", ephemeral=True)
        
        # Si ya está sonando, solo agregamos a la cola
        if voice.is_playing() or voice.is_paused(): # Si está sonando algo
            print(f"[PLAY] Ya está sonando algo. Añadiendo a la cola.") 
            queue["tracks"].append({"title": title, "webpage_url": webpage_url, "duration": duration, "thumbnail": thumbnail})
            
            q_msg = await interaction.followup.send(f"📝 Añadido a la cola: **{title}**")
            try:
                await q_msg.delete(delay=10)
            except: pass
            
            # Cancelar disconnect
            if interaction.guild.id in disconnect_tasks:
                disconnect_tasks[interaction.guild.id].cancel()
                del disconnect_tasks[interaction.guild.id]
                
            return

        # Si NO está sonando, reproducimos inmediatamente
        queue["tracks"].append({"title": title, "webpage_url": webpage_url, "duration": duration, "thumbnail": thumbnail})
        queue["index"] = len(queue["tracks"]) - 1 # El último índice

        # Reproducir el track
        real_title, real_duration, thumbnail = await play_track_in_guild(interaction.guild, queue["tracks"][queue["index"]])

        # Embed minimalista
        chn = interaction.user.voice.channel.name if interaction.user.voice else "Voz"
        embed = create_minimal_embed(real_title, webpage_url, real_duration, 0, thumbnail, interaction.user.name, channel_name=chn)
        view = PlayerView(interaction.guild.id)
        
        # Limpiar anterior antes de mandar nuevo
        await cleanup_previous_message(interaction.guild.id)

        # Enviamos mensaje y guardamos la referencia para editarla luego
        # followup.send devuelve un webhook_message que se puede editar? Sí.
        message = await interaction.followup.send(embed=embed, view=view)
        print(f"[PLAY] Reproducción iniciada exitosamente")

        # Guardar mensaje en audio_sources
        if interaction.guild.id in audio_sources:
                audio_sources[interaction.guild.id]["message"] = message

        # Iniciar tarea de actualización BACKGROUND
        if real_duration > 0:
            task = bot.loop.create_task(update_message_task(message, audio_sources[interaction.guild.id]["start_time"], real_duration, real_title, voice))
            audio_sources[interaction.guild.id]["task"] = task

    except Exception as e:
        print(f"[PLAY] ERROR al reproducir: {e}")
        await interaction.followup.send(f"Error al reproducir: {e}", ephemeral=True)


async def play_track_in_guild(guild: discord.Guild, track: dict, start_offset=0):
    """
    Reproduce un track (dict con title/webpage_url) en el voice_client del guild.
    start_offset: Tiempo en segundos desde donde empezar (para seek).
    """
    voice = guild.voice_client
    if voice is None:
        print("[PLAY_TRACK] No hay voice_client")
        return "No estoy conectado a un canal de voz.", 0

    # Si ya está sonando algo, lo paramos (importante para seek)
    if voice.is_playing() or voice.is_paused():
        voice.stop()

    # Conseguir la URL de stream y el título (y thumbnail)
    # buscar_audio devuelve 5 valores ahora
    stream_url, real_title, duration, thumbnail, webpage_url = buscar_audio(track["webpage_url"])
    print(f"[PLAY_TRACK] Reproduciendo: {real_title} desde {start_offset}s")
    logger.info("[QUEUE] Ahora suena: %s (offset: %s)", real_title, start_offset)

    # Guardar en historial
    if guild.id in music_queues:
        hist = music_queues[guild.id]["history"]
        # Guardar URL original para el historial, no el stream
        hist_url = track.get("webpage_url", stream_url)
        hist.insert(0, {"title": real_title, "url": hist_url, "timestamp": 
        datetime.now()})
        if len(hist) > 15: hist.pop() # Máximo 15

    # Opciones de FFmpeg con offset
    current_opts = FFMPEG_OPTIONS.copy()
    # solo añadimos el reconnect_at_eof a la config standard
    current_opts["before_options"] = f"-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -reconnect_at_eof 1 -ss {start_offset}"

    # Crear el source (Usamos PCMAudio para poder controlar el volumen)
    # FFmpegOpusAudio no soporta PCMVolumeTransformer
    try:
        source = discord.FFmpegPCMAudio(
            stream_url,
            executable=FFMPEG_PATH,
            **current_opts
        )
        print("[PLAY_TRACK] Fuente creada con FFmpegPCMAudio")
    except Exception as e:
        print(f"[PLAY_TRACK] Error creando fuente: {e}")
        return f"Error de audio: {e}", 0

    # Ajustar volumen (Normalizar a 50%)
    source = discord.PCMVolumeTransformer(source, volume=0.5)

    # Guardar source actual sin perder la referencia al mensaje anterior
    if guild.id not in audio_sources:
        audio_sources[guild.id] = {}
        
    # Actualizamos valores, manteniendo lo que hubiera (ej: message, task)
    audio_sources[guild.id].update({
        "source": source,
        "title": real_title,
        "url": track.get("webpage_url", stream_url), # URL ORIGINAL!!
        "duration": duration,
        "start_time": time.time(),
        "offset": start_offset, 
        "thumbnail": thumbnail 
    })
    
    # Actualizar estado del bot (Rich Presence)
    await update_bot_status(real_title)

    def after_playing(error):
        # Si se paró manualmente (por seek), no hacemos play_next
        # ¿Cómo sabemos si fue por seek? 
        # Podemos marcar un flag en audio_sources o revisar si sigue conectado
        # Pero `stop()` dispara esto. 
        # TRUCO: Cuando hacemos seek, llamaremos a play_track_in_guild que llama a stop().
        # Para evitar que salte de canción, el seek debe gestionar esto o play_next
        # debe chequear si "debe" saltar.
        
        # Estrategia simple: play_next siempre salta.
        # Si hacemos SEEK, NO queremos que salte al siguiente.
        # Solución: En función seek, antes de play, ponemos un flag "seeking".
        
        if guild.id in audio_sources and audio_sources[guild.id].get("seeking", False):
            print("[AFTER_PLAYING] Ignorando porque estamos haciendo SEEK.")
            return

        if error:
            print(f"[PLAY_TRACK] Reproducción finalizada con error: {error}")
        
        # Llamar a play_next para la siguiente canción
        fut = asyncio.run_coroutine_threadsafe(play_next(guild), bot.loop)
        try:
            fut.result()
        except Exception as e:
             pass

    voice.play(source, after=after_playing)
    return real_title, duration, thumbnail


async def play_next(guild: discord.Guild):
    """
    Avanza al siguiente track en la cola y lo reproduce.
    """
    if guild.id not in music_queues: # Si no hay cola
        return
    
    queue = music_queues[guild.id] 
    voice = guild.voice_client

    if not voice:
        return

    # Avanzar índice
    queue["index"] += 1

    # Verificar si hay más canciones
    # Verificar si hay más canciones
    if queue["index"] >= len(queue["tracks"]):
        # FIN DE LA COLA -> AUTOPLAY INTELIGENTE
        print("[AUTOPLAY] Cola terminada. Buscando recomendación...")
        
        # Notificar al usuario
        channel = queue.get("channel")
        autoplay_msg = None
        if channel:
            try:
                autoplay_msg = await channel.send("🎲 **Autoplay:** Buscando canción aleatoria...")
            except: pass
        
        try:
            last_track = queue["tracks"][-1]
            last_title = last_track.get("title", "")
            
            # Limpiar título básico (quitar (Official Video) etc)
            # Limpiar título básico (quitar (Official Video) etc)
            clean_title = last_title.split("(")[0].split("[")[0].strip()
            search_query = f"{clean_title} official audio" # Búsqueda un poco más específica
            
            print(f"[AUTOPLAY] Buscando recomendaciones para: {clean_title}...")

            # Buscar 5 resultados y SIEMPRE elegir uno diferente
            # Lógica personalizada inline para no romper buscar_audio estándar
            def get_recommendation(query):
                with YoutubeDL({"format": "bestaudio", "noplaylist": True, "quiet": True}) as ydl_rec:
                   try:
                       # Buscar 5 videos
                       info_rec = ydl_rec.extract_info(f"ytsearch5:{query}", download=False)
                       if "entries" in info_rec:
                           entries = info_rec["entries"]
                           if not entries or len(entries) == 0:
                               return None
                           
                           # Filtrar válidos
                           valid = [e for e in entries if e]
                           if not valid:
                               return None
                           
                           # ESTRATEGIA: Saltar SIEMPRE el primero (es la misma canción)
                           # Si hay más de 1, elegir uno aleatorio del resto
                           if len(valid) > 1:
                               # Elegir random entre índices 1-4
                               import random
                               chosen = random.choice(valid[1:])
                           else:
                               # Solo hay 1, devolver ese (fallback)
                               chosen = valid[0]
                           
                           return chosen.get("url"), chosen.get("title"), chosen.get("duration"), chosen.get("thumbnail"), chosen.get("webpage_url")
                   except Exception as e:
                       print(f"[AUTOPLAY_SEARCH] Error: {e}")
                       return None
                return None

            res = await bot.loop.run_in_executor(None, lambda: get_recommendation(search_query))
            
            if res:
                stream_u, new_title, new_dur, new_thumb, new_page_url = res
                
                # Añadir a la cola
                queue["tracks"].append({
                    "title": new_title, 
                    "webpage_url": new_page_url, 
                    "duration": new_dur, 
                    "thumbnail": new_thumb
                })
                print(f"[AUTOPLAY] Añadido auto: {new_title}")
            else:
                print("[AUTOPLAY] No se encontraron recomendaciones.")
                # Borrar mensaje de búsqueda si no encontramos nada
                if autoplay_msg:
                    try: await autoplay_msg.delete()
                    except: pass
                return
            
            # Borrar mensaje de "Buscando..." ya que encontramos una
            if autoplay_msg:
                try: await autoplay_msg.delete()
                except: pass
            
            
        except Exception as e:
            print(f"[AUTOPLAY] Error: {e}")
            # Si falla, dejamos que el timer de desconexión haga su trabajo
            return

    # Reproducir track actual (ya sea siguiente normal o autoplay)
    track = queue["tracks"][queue["index"]]
    print(f"[PLAY_NEXT] Reproduciendo siguiente: {track['title']}")
        
    real_title, real_duration, thumbnail = await play_track_in_guild(guild, track)
    
    # Enviar mensaje al canal original
    channel = queue.get("channel")
    if channel:
        # Embed Minimalista
        # Recuperar URL del track para el embed
        track_url = track.get("webpage_url", "https://discord.com")
        embed = create_minimal_embed(real_title, track_url, real_duration, 0, thumbnail)
        
        # Reenviamos la view para que los botones sigan disponibles abajo
        view = PlayerView(guild.id)
        try:
            # Limpiar anterior
            await cleanup_previous_message(guild.id)
            
            message = await channel.send(embed=embed, view=view)
            
            # Guardar referencia
            if guild.id in audio_sources:
                audio_sources[guild.id]["message"] = message

            # Iniciar tarea de actualización BACKGROUND
            if real_duration > 0 and guild.id in audio_sources:
                 task = bot.loop.create_task(update_message_task(message, audio_sources[guild.id]["start_time"], real_duration, real_title, guild.voice_client))
                 audio_sources[guild.id]["task"] = task
                 
        except Exception as e:
            print(f"[PLAY_NEXT] No se pudo enviar mensaje: {e}")

    else:
        print("[PLAY_NEXT] Fin de la cola.")
        # Opcional: Loop
        if queue.get("loop", False) and len(queue["tracks"]) > 0:
             queue["index"] = -1 # Se pondrá en 0 en la recursión? No, play_next hace +=1.
             # Recursividad cuidado. Mejor:
             queue["index"] = -1
             await play_next(guild) # Avanza a 0 y reproduce
        else:
             channel = queue.get("channel")
             if channel:
                 await channel.send("✅ Fin de la cola de reproducción.") 










class PlayerView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        queue = music_queues.get(self.guild_id)
        if not queue:
            return await interaction.response.send_message("No hay cola activa.", ephemeral=True)

        voice = interaction.guild.voice_client
        if voice is None:
            return await interaction.response.send_message("No estoy en un canal de voz.", ephemeral=True)

        # Queremos ir al anterior.
        # play_next incrementa +1.
        # Si queremos index - 1, necesitamos settear index - 2.
        new_index = queue["index"] - 2
        
        # Validar límites
        if new_index < -1: 
            # Si estamos en 0 (index=0), new_index=-2. play_next hará -2+1=-1 (invalido).
            # Loop al final? O nos quedamos en el inicio?
            # Comportamiento simple: Si estamos en el principio, reiniciar la canción.
            new_index = -1 
        
        queue["index"] = new_index
        
        # Detener la música actual disparará after_playing -> play_next
        if voice.is_playing() or voice.is_paused():
            voice.stop()
        else:
            # Si no suena nada, forzamos play_next manualmente
            await play_next(interaction.guild)

        await interaction.response.send_message("⏮️ Retrocediendo...", ephemeral=True)

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.secondary)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice = interaction.guild.voice_client
        if not voice:
            return await interaction.response.send_message("No estoy en un canal de voz.", ephemeral=True)

        if voice.is_playing():
            voice.pause()
            txt = "⏸️ Pausado."
        elif voice.is_paused():
            voice.resume()
            txt = "▶️ Reanudado."
        else:
            txt = "No hay nada reproduciéndose."

        await interaction.response.send_message(txt, ephemeral=True)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        queue = music_queues.get(self.guild_id)
        if not queue:
            return await interaction.response.send_message("No hay cola activa.", ephemeral=True)

        voice = interaction.guild.voice_client
        if voice is None:
            return await interaction.response.send_message("No estoy en un canal de voz.", ephemeral=True)

        # play_next incrementa +1 automáticamente.
        # Si queremos ir al siguiente, simplemente paramos el actual.
        # El índice actual ya es correcto. play_next hará index + 1.
        
        if voice.is_playing() or voice.is_paused():
            voice.stop()
        else:
            await play_next(interaction.guild)

        await interaction.response.send_message("⏭️ Saltando...", ephemeral=True)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.secondary)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice = interaction.guild.voice_client
        if not voice:
            return await interaction.response.send_message("No estoy en un canal de voz.", ephemeral=True)

        if voice.is_playing() or voice.is_paused():
            voice.stop()

        audio_sources.pop(self.guild_id, None)
        music_queues.pop(self.guild_id, None)

        await interaction.response.send_message("⏹️ Detenido.", ephemeral=False)



@bot.event
async def on_ready():
    print(f"Bot listo como {bot.user}") # Muestra el nombre del bot
    print(f"Bot ID: {bot.user.id}")
    
    # Sincronizar comandos globalmente (puede tardar hasta 1 hora)
    try:
        db.init_db() # Inicializar base de datos
        print("Base de datos inicializada")
        
        if not clean_chat_task.is_running():
             clean_chat_task.start()
             print("Tarea de auto-limpieza iniciada.")
        
        if not daily_history_cleanup.is_running():
             # Calcular cuánto falta para medianoche y empezar ahí
             now = datetime.now()
             midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
             # Si ya pasó medianoche hoy, programar para mañana
             if now >= midnight:
                 from datetime import timedelta
                 midnight += timedelta(days=1)
             
             # Calcular segundos hasta medianoche
             seconds_until_midnight = (midnight - now).total_seconds()
             print(f"Historial se limpiará en {seconds_until_midnight/3600:.1f} horas (a las 00:00)")
             
             # Iniciar la tarea (se ejecutará cada 24h desde ahora)
             daily_history_cleanup.start()
             print("Tarea de limpieza de historial iniciada.")
             
        synced = await bot.tree.sync() # Sincroniza los comandos slash
        print(f"Sincronizados {len(synced)} comandos globalmente")
    except Exception as e:
        print(f"Error al sincronizar comandos: {e}")


    # guild_id = 1368215601125789847  # Reemplaza con el ID de tu servidor

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
        await interaction.guild.voice_client.disconnect() # Se desconecta el bot del canal de voz
        await interaction.response.send_message("Desconectado.") # Se envía un mensaje de confirmación
    else: # Si el bot no está en un canal de voz, se envía un mensaje de error
        await interaction.response.send_message("No estoy en un canal de voz.", ephemeral=True) # Se envía un mensaje de error


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
        
        # Limpiar la cola también al detener (opcional, pero lógico en stop total)
        if interaction.guild.id in music_queues:
            music_queues[interaction.guild.id]["tracks"] = []
            music_queues[interaction.guild.id]["index"] = 0

        await interaction.response.send_message("⏹️ Detenido y cola limpiada.") # Se envía un mensaje de confirmación
    else: # Si el bot no está reproduciendo ni pausado, se envía un mensaje de error
        await interaction.response.send_message("No hay nada reproduciéndose.", ephemeral=True) # Se envía un mensaje de error


@bot.tree.command(name="move", description="Mueve el bot a tu canal de voz actual sin cortar la música")
async def move(interaction: discord.Interaction):
    if interaction.user.voice is None:
        return await interaction.response.send_message("No estás en un canal de voz.", ephemeral=True)
    
    voice = interaction.guild.voice_client
    target_channel = interaction.user.voice.channel

    if not voice:
        # Si el bot no está conectado, nos conectamos normal
        await target_channel.connect()
        return await interaction.response.send_message(f"✅ Conectado a **{target_channel.name}**.")
    
    if voice.channel.id == target_channel.id:
        return await interaction.response.send_message("Ya estoy en tu canal.", ephemeral=True)
    
    # Moverse sin desconectar
    await voice.move_to(target_channel)
    
    # Actualizar el canal de notificaciones si hay cola
    if interaction.guild.id in music_queues:
        music_queues[interaction.guild.id]["channel"] = interaction.channel
        
    await interaction.response.send_message(f"🚚 Movido a **{target_channel.name}**.")

@bot.tree.command(name="playlist", description="Carga una playlist entera de YouTube")
@app_commands.describe(url="URL de la playlist")
async def playlist(interaction: discord.Interaction, url: str):
    await interaction.response.defer()
    
    voice_channel = interaction.user.voice.channel
    if not voice_channel:
        return await interaction.followup.send("¡Debes estar en un canal de voz!")
    
    # Conectar si hace falta
    if not interaction.guild.voice_client:
        await voice_channel.connect()
    
    tracks, playlist_title = buscar_playlist(url)
    
    if not tracks:
         return await interaction.followup.send(f"❌ Error cargando playlist: {playlist_title}")
         
    # Añadir a cola
    if interaction.guild.id not in music_queues:
        music_queues[interaction.guild.id] = {
            "tracks": [], "index": 0, "channel": interaction.channel, "loop": False, "history": []
        }
        
    queue = music_queues[interaction.guild.id]
    
    # Añadir canciones
    count = 0
    for t in tracks:
        queue["tracks"].append(t)
        count += 1
        
    await interaction.followup.send(f"✅ Añadidas **{count}** canciones de la lista **{playlist_title}**.")
    
    # Si no suena nada, darle caña
    voice = interaction.guild.voice_client
    if not voice.is_playing() and not voice.is_paused():
        # Ajustar index si acabamos de crear la cola
        if len(queue["tracks"]) == count: # Cola nueva
            queue["index"] = 0
            
        # Reproducir tracks[0] o el que toque
        # Si la cola tenía cosas pero ya acabó, index estará al final
        if queue["index"] >= len(queue["tracks"]) - count:
             # Si estaba parada al final, movemos index al principio de lo nuevo
             queue["index"] = len(queue["tracks"]) - count
             
        track = queue["tracks"][queue["index"]]
        real_title, real_duration, thumbnail = await play_track_in_guild(interaction.guild, track)
        
        # Enviar embed inicial (reutilizando lógica play)
        try:
             # Cleanup y mensaje
             await cleanup_previous_message(interaction.guild.id)
             progress_bar = create_progress_bar(0, real_duration)
             embed = discord.Embed(title="🎵 Reproduciendo Playlist", description=f"**{real_title}**\n\n{progress_bar}", color=discord.Color.blurple())
             if thumbnail: embed.set_thumbnail(url=thumbnail)
             msg = await interaction.followup.send(embed=embed, view=PlayerView(interaction.guild.id))
             
             if real_duration > 0:
                 task = bot.loop.create_task(update_message_task(msg, time.time(), real_duration, real_title, voice))
                 audio_sources[interaction.guild.id] = audio_sources.get(interaction.guild.id, {})
                 audio_sources[interaction.guild.id]["message"] = msg
                 audio_sources[interaction.guild.id]["start_time"] = time.time()
                 audio_sources[interaction.guild.id]["task"] = task
        except Exception as e:
            print(f"Error UI Playlist: {e}")

@bot.tree.command(name="history", description="Muestra las canciones reproducidas hoy")
async def historial(interaction: discord.Interaction):
    q = music_queues.get(interaction.guild.id)
    if not q or not q["history"]:
        return await interaction.response.send_message("El historial está vacío.", ephemeral=True)
    
    # Filtrar solo canciones de hoy
    today_history = get_today_history(q["history"])
    
    if not today_history:
        return await interaction.response.send_message("📭 No has escuchado nada hoy todavía.", ephemeral=True)
    
    # Formatear fecha de hoy
    today_date = datetime.now().strftime("%d/%m/%Y")
    embed = discord.Embed(
        title=f"📜 Historial de Hoy ({today_date})",
        color=discord.Color.gold()
    )
    
    desc = ""
    # Mostrar las canciones de hoy (máximo 15 para no saturar)
    display_history = today_history[:15]
    
    for i, item in enumerate(display_history, 1):
        desc += f"**{i}.** [{item['title']}]({item['url']})\n"
    
    if len(today_history) > 15:
        desc += f"\n*... y {len(today_history) - 15} más*"
    
    embed.description = desc
    embed.set_footer(text=f"Total de canciones hoy: {len(today_history)}")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ========== VISTAS INTERACTIVAS (UI) ==========

class PlaylistSelectionView(discord.ui.View):
    """
    Vista para seleccionar qué canciones guardar.
    Tiene un Select Menu y un botón de Confirmar.
    """
    def __init__(self, tracks, name, guild_id, user_id, method="save_new"):
        super().__init__(timeout=60)
        self.tracks = tracks # Lista completa de tracks
        self.name = name
        self.guild_id = guild_id
        self.user_id = user_id
        self.method = method # "save_new", "overwrite", "append"
        self.selected_indices = []

        # Discord limita los Select Menus a 25 opciones.
        # Vamos a coger las últimas 25 (o primeras 25?) -> Primeras 25 (lo que sonó y está sonando)
        # O mejor: Las 25 más recientes en la cola.
        # Si hay más de 25, cortamos por ahora (limitación de UI simple).
        self.display_tracks = tracks[:25]

        # Crear el Select Menu dinámicamente
        options = []
        for i, t in enumerate(self.display_tracks):
            # Acortar título si es muy largo
            label = t["title"][:95]
            options.append(discord.SelectOption(
                label=label,
                value=str(i),
                description=f"Posición {i+1}",
                default=True # Por defecto todas seleccionadas? Sí.
            ))

        self.select_menu = discord.ui.Select(
            placeholder="Selecciona canciones a guardar (max 25)...",
            min_values=1,
            max_values=len(options),
            options=options
        )
        self.select_menu.callback = self.select_callback
        self.add_item(self.select_menu)

    async def select_callback(self, interaction: discord.Interaction):
        # Actualizar selección
        self.selected_indices = [int(v) for v in self.select_menu.values]
        await interaction.response.defer() # Acknowledge sin hacer nada

    @discord.ui.button(label="💾 Confirmar Guardado", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Si no tocó el menú, self.selected_indices puede estar vacío, pero el default era True...
        # Wait, en discord.py los defaults visuales no rellenan values automáticamente si no interactúas?
        # Asumiremos que si no toca, quiere AL MENOS lo que marcó.
        # Mejor estrategia: Si values está vacío, miramos los defaults.
        
        final_indices = self.selected_indices
        if not final_indices:
             # Si no seleccionó nada explícitamente, asumimos TODAS (como viene pre-marcado)
             final_indices = list(range(len(self.display_tracks)))
        
        final_tracks = [self.display_tracks[i] for i in final_indices]
        
        msg = "" 
        if self.method == "append":
             success, txt = db.add_songs_to_playlist(self.name, self.guild_id, self.user_id, final_tracks)
             msg = txt
        else: # save_new o overwrite (db.save_playlist maneja ambos, sobrescribe si existe)
             success, txt = db.save_playlist(self.name, self.guild_id, self.user_id, final_tracks)
             msg = txt
        
        # Desactivar todo
        self.clear_items()
        await interaction.response.edit_message(content=f"✅ {msg}", view=self)


class SaveMethodView(discord.ui.View):
    """
    Pregunta si sobrescribir o añadir si la playlist existe.
    """
    def __init__(self, name, guild_id, user_id, tracks):
        super().__init__(timeout=60)
        self.name = name
        self.guild_id = guild_id
        self.user_id = user_id
        self.tracks = tracks # Tracks candidatos
        self.value = None

    @discord.ui.button(label="Sobrescribir (Borrar anterior)", style=discord.ButtonStyle.danger)
    async def overwrite(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Ir a selección, modo overwrite
        await interaction.response.send_message("Selecciona qué canciones guardar en la NUEVA versión:", 
                                                view=PlaylistSelectionView(self.tracks, self.name, self.guild_id, self.user_id, "overwrite"),
                                                ephemeral=True)
        self.stop()

    @discord.ui.button(label="Añadir al final", style=discord.ButtonStyle.blurple)
    async def append(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Ir a selección, modo append
        await interaction.response.send_message("Selecciona qué canciones AÑADIR al final:", 
                                                view=PlaylistSelectionView(self.tracks, self.name, self.guild_id, self.user_id, "append"),
                                                ephemeral=True)
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Operación cancelada.", view=None)
        self.stop()

# MODAL PARA SEEK
class SeekModal(discord.ui.Modal, title="Ir a minuto específico"):
    time_input = discord.ui.TextInput(
        label="Tiempo (mm:ss o segundos)",
        placeholder="Ej: 02:30 o 150",
        required=True
    )

    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        # Parsear tiempo
        inp = self.time_input.value
        seconds = 0
        try:
            if ":" in inp:
                parts = inp.split(":")
                seconds = int(parts[0]) * 60 + int(parts[1])
            else:
                seconds = int(inp)
        except:
            return await interaction.response.send_message("Formato inválido. Usa mm:ss (ej 1:30) o segundos (ej 90).", ephemeral=True)
        
        await seek_to_time(interaction, seconds)


async def seek_to_time(interaction: discord.Interaction, target_seconds: int):
    """Lógica para mover la canción."""
    guild = interaction.guild
    if guild.id not in audio_sources:
        return await interaction.response.send_message("No hay nada sonando.", ephemeral=True)
    
    info = audio_sources[guild.id]
    duration = info["duration"]
    
    # Validar límites
    if target_seconds < 0: target_seconds = 0
    if duration > 0 and target_seconds >= duration: 
        return await interaction.response.send_message("No puedes adelantar más allá del final.", ephemeral=True)

    await interaction.response.defer() # Porque vamos a tardar un poco
    
    # Marcar que estamos haciendo seek para que after_playing no salte de canción
    audio_sources[guild.id]["seeking"] = True
    
    # Recuperar track actual de la cola para tener la URL original limpia?
    # Ya tenemos info["url"] que es el stream_url. 
    # OJO: `stream_url` de yt-dlp a veces caduca. Lo ideal sería recuperar el track de la cola.
    queue = music_queues.get(guild.id)
    if not queue: return
    
    track = queue["tracks"][queue["index"]]
    
    # Reproducir desde offset
    real_title, _, thumbnail = await play_track_in_guild(guild, track, start_offset=target_seconds)
    
    # Quitar el flag de seeking (se reinicializa en play_track_in_guild en realidad, 
    # porque sobrescribe audio_sources[guild.id], así que "seeking" se pierde, que es lo que queremos)
    
    # Actualizar mensaje con nueva barra
    progress_bar = create_progress_bar(target_seconds, duration)
    embed = discord.Embed(
        title="⏩ Saltando tiempo",
        description=f"**{real_title}**\n\n{progress_bar}",
        color=discord.Color.gold()
    )
    if thumbnail: embed.set_thumbnail(url=thumbnail)
    
    # Limpiar anterior
    await cleanup_previous_message(guild.id)

    # Enviamos nuevo mensaje de estado
    msg = await interaction.followup.send(embed=embed, view=PlayerView(guild.id))
    
    # Guardar referencia
    audio_sources[guild.id]["message"] = msg
    
    # Reiniciar updater
    if duration > 0:
        task = bot.loop.create_task(update_message_task(msg, time.time(), duration, real_title, guild.voice_client))
        audio_sources[guild.id]["task"] = task


class PlayerView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary, row=0)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⏮️ Retrocediendo canción...", ephemeral=True)
        
        queue = music_queues.get(self.guild_id)
        if not queue: return
        voice = interaction.guild.voice_client
        
        new_index = queue["index"] - 2
        if new_index < -1: new_index = -1
        queue["index"] = new_index
        
        if voice.is_playing() or voice.is_paused(): voice.stop()
        else: await play_next(interaction.guild)

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.success, row=0)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice = interaction.guild.voice_client
        if not voice: return await interaction.response.send_message("No estoy conectado.", ephemeral=True)
        
        if voice.is_playing():
            voice.pause()
            txt = "⏸️ Pausado."
        elif voice.is_paused():
            voice.resume()
            txt = "▶️ Reanudado."
        else: txt = "Nada sonando."
        await interaction.response.send_message(txt, ephemeral=True)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, row=0)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Respondemos PRIMERO
        await interaction.response.send_message("⏭️ Saltando...", ephemeral=True)
        
        queue = music_queues.get(self.guild_id)
        if not queue: return
        voice = interaction.guild.voice_client
        if voice.is_playing() or voice.is_paused(): voice.stop()
        else: await play_next(interaction.guild)

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.secondary, row=0)
    async def shuffle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        queue = music_queues.get(self.guild_id)
        if not queue: return await interaction.response.send_message("No hay cola.", ephemeral=True)
        
        current_idx = queue["index"]
        # Si estamos al final, no hay nada que mezclar
        if current_idx >= len(queue["tracks"]) - 1:
             return await interaction.response.send_message("⚠️ No hay canciones siguientes para mezclar.", ephemeral=True)
             
        # Separar: Lo ya sonado+actual VS Lo que viene
        current_and_past = queue["tracks"][:current_idx+1]
        upcoming = queue["tracks"][current_idx+1:]
        
        random.shuffle(upcoming)
        
        queue["tracks"] = current_and_past + upcoming
        await interaction.response.send_message("🔀 Cola mezclada (próximas canciones).", ephemeral=True)

    @discord.ui.button(emoji="❤️", style=discord.ButtonStyle.secondary, row=0)
    async def love_song(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Guardar en favoritos la canción actual
        if self.guild_id not in audio_sources: 
            return await interaction.response.send_message("No está sonando nada.", ephemeral=True)
        
        info = audio_sources[self.guild_id]
        track = {
            "title": info["title"],
            "webpage_url": info["url"],
            "duration": info.get("duration", 0),  # Usar .get() para evitar KeyError
            "thumbnail": info.get("thumbnail")
        }
        
        success, msg = db.save_favorite(interaction.user.id, track)
        await interaction.response.send_message(f"❤️ {msg}", ephemeral=True)

    @discord.ui.button(emoji="📍", label="Ir a...", style=discord.ButtonStyle.secondary, row=1)
    async def seek_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SeekModal(self.guild_id))

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, row=1)
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
         await interaction.response.send_message("⏹️ Stop.", ephemeral=True)
         # Lógica stop
         voice = interaction.guild.voice_client
         if voice: voice.stop()
         if interaction.guild.id in music_queues:
             music_queues[interaction.guild.id]["tracks"] = []


@bot.tree.command(name="favorites", description="Reproduce tus canciones favoritas")
async def favorites(interaction: discord.Interaction):
    # Obtener favoritos
    favs = db.get_favorites(interaction.user.id)
    if not favs:
        return await interaction.response.send_message("💔 No tienes favoritos guardados aún. Usa el botón ❤️ cuando suene algo que te guste.", ephemeral=True)
        
    # Añadir a la cola
    if interaction.guild.id not in music_queues:
         music_queues[interaction.guild.id] = {
             "tracks": [], "index": 0, "channel": interaction.channel, "loop": False, "history": []
         }
    
    queue = music_queues[interaction.guild.id]
    
    # Shuffle opcional? Por ahora tal cual
    import random
    random.shuffle(favs) # Mejor aleatorio para que no sea siempre igual
    
    for f in favs:
        queue["tracks"].append(f)
        
    await interaction.response.send_message(f"❤️ Cargadas **{len(favs)}** canciones favoritas (Aleatorio).")
    
    # Si no suena nada, darle
    voice = interaction.guild.voice_client
    if voice and not voice.is_playing() and not voice.is_paused():
        # Ajustar index si la cola era nueva
        if len(queue["tracks"]) == len(favs):
             queue["index"] = 0
             
        track = queue["tracks"][queue["index"]]
        real_title, real_duration, thumbnail = await play_track_in_guild(interaction.guild, track)
        
        # UI Inicial (reutilizada)
        try:
             await cleanup_previous_message(interaction.guild.id)
             progress_bar = create_progress_bar(0, real_duration)
             embed = discord.Embed(title="❤️ Reproduciendo Favoritos", description=f"**{real_title}**\n\n{progress_bar}", color=discord.Color.red())
             if thumbnail: embed.set_thumbnail(url=thumbnail)
             msg = await interaction.followup.send(embed=embed, view=PlayerView(interaction.guild.id))
             
             if real_duration > 0:
                 task = bot.loop.create_task(update_message_task(msg, time.time(), real_duration, real_title, voice))
                 audio_sources[interaction.guild.id] = audio_sources.get(interaction.guild.id, {})
                 audio_sources[interaction.guild.id]["message"] = msg
                 audio_sources[interaction.guild.id]["start_time"] = time.time()
                 audio_sources[interaction.guild.id]["task"] = task
        except Exception as e:
            print(f"Error UI Favorites: {e}")




# COMANDOS DE BASE DE DATOS

@bot.tree.command(name="save", description="Guarda canciones de la cola en una playlist personal")
@app_commands.describe(name="Nombre de la playlist")
async def save(interaction: discord.Interaction, name: str):
    queue = music_queues.get(interaction.guild.id)
    if not queue or not queue["tracks"]:
        return await interaction.response.send_message("No hay nada en la cola para guardar.", ephemeral=True)
    
    tracks = queue["tracks"]
    
    # 1. Chequear si existe la playlist PARA ESTE USUARIO
    exists_id = db.check_playlist_exists(name, interaction.guild.id, interaction.user.id)
    
    if exists_id:
        # Preguntar qué hacer
        view = SaveMethodView(name, interaction.guild.id, interaction.user.id, tracks)
        await interaction.response.send_message(f"La playlist **{name}** ya existe. ¿Qué quieres hacer?", view=view, ephemeral=True)
    else:
        # No existe, vamos directo a selección
        view = PlaylistSelectionView(tracks, name, interaction.guild.id, interaction.user.id, "save_new")
        await interaction.response.send_message(f"Creando playlist **{name}**. Selecciona qué canciones guardar:", view=view, ephemeral=True)


@bot.tree.command(name="load", description="Carga una playlist guardada")
@app_commands.describe(name="Nombre de la playlist")
async def load(interaction: discord.Interaction, name: str):
    # Pasamos user_id para cargar SUS playlists
    tracks = db.get_playlist(name, interaction.guild.id, interaction.user.id)
    if not tracks:
        return await interaction.response.send_message(f"No tienes ninguna playlist llamada '{name}'.", ephemeral=True)
    
    # ... Resto del código de load ...

    if interaction.user.voice is None:
        return await interaction.response.send_message("Debes estar en un canal de voz.", ephemeral=True)

    await interaction.response.defer()

    # Lógica similar a playlist:
    
    # 1. Asegurar cola
    if interaction.guild.id not in music_queues:
        music_queues[interaction.guild.id] = {
            "tracks": [],
            "index": 0,
            "channel": interaction.channel,
            "loop": False
        }
    
    # 2. Conectar voz
    voice = interaction.guild.voice_client
    if voice is None:
        channel = interaction.user.voice.channel
        await channel.connect()
        voice = interaction.guild.voice_client

    queue = music_queues[interaction.guild.id]
    
    # Estrategia: "Añadir al final" o "Reemplazar"?
    # El usuario dijo "quiero hacer una lista... con un comando pueda hacer una lista".
    # Generalmente cargar una playlist reemplaza o añade. Haremos APPEND (añadir al final) para ser menos destructivos,
    # salvo que la cola esté vacía.
    
    was_empty = len(queue["tracks"]) == 0
    
    queue["tracks"].extend(tracks) # Añadimos tracks
    
    await interaction.followup.send(f"📂 Playlist '{name}' cargada ({len(tracks)} canciones añadidas).")

    # Si NO estaba sonando nada, empezamos a reproducir la primera de las nuevas
# === SERVER PLAYLISTS (Globales) ===

class ServerPlaylistGroup(app_commands.Group):
    """Comandos para gestionar playlists del servidor."""

    @app_commands.command(name="save", description="[Admin] Guarda la cola actual como playlist del servidor")
    @app_commands.describe(name="Nombre de la playlist")
    async def save(self, interaction: discord.Interaction, name: str):
        # Check Admin
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Solo administradores pueden guardar playlists del servidor.", ephemeral=True)

        queue = music_queues.get(interaction.guild.id)
        if not queue or not queue["tracks"]:
            return await interaction.response.send_message("No hay nada en la cola para guardar.", ephemeral=True)
        
        success, msg = db.save_server_playlist(name, interaction.guild.id, interaction.user.id, queue["tracks"])
        await interaction.response.send_message(f"📢 {msg}")

    @app_commands.command(name="load", description="Carga una playlist del servidor")
    @app_commands.describe(name="Nombre de la playlist")
    async def load(self, interaction: discord.Interaction, name: str):
        tracks = db.get_server_playlist(name, interaction.guild.id)
        if not tracks:
            return await interaction.response.send_message(f"No existe la playlist de servidor '{name}'.", ephemeral=True)
        
        if interaction.user.voice is None:
            return await interaction.response.send_message("Debes estar en un canal de voz.", ephemeral=True)

        await interaction.response.defer()

        # Init cola
        if interaction.guild.id not in music_queues:
            music_queues[interaction.guild.id] = {
                "tracks": [], "index": 0, "channel": interaction.channel, "loop": False, "history": []
            } # Added history init just in case
        
        # Conectar
        voice = interaction.guild.voice_client
        if voice is None:
            await interaction.user.voice.channel.connect()
            voice = interaction.guild.voice_client

        queue = music_queues[interaction.guild.id]
        
        # Añadir
        was_empty = len(queue["tracks"]) == 0
        queue["tracks"].extend(tracks)
        
        await interaction.followup.send(f"📂 Playlist de Servidor '{name}' cargada ({len(tracks)} canciones).")

        # Reproducir si estaba parado
        if not voice.is_playing() and not voice.is_paused():
            if was_empty:
                queue["index"] = 0
            else:
                queue["index"] += 1
            
            # Play
            track = queue["tracks"][queue["index"]]
            real_title, real_duration, thumbnail = await play_track_in_guild(interaction.guild, track)
            
            # UI
            embed = discord.Embed(title="📢 Reproduciendo Playlist de Servidor", description=track["title"], color=discord.Color.gold())
            if thumbnail: embed.set_thumbnail(url=thumbnail)
            view = PlayerView(interaction.guild.id)
            msg = await interaction.channel.send(embed=embed, view=view)
            
            if real_duration > 0:
                 task = bot.loop.create_task(update_message_task(msg, time.time(), real_duration, real_title, voice))
                 audio_sources[interaction.guild.id] = {"message": msg, "start_time": time.time(), "task": task, "title": real_title, "url": track["webpage_url"], "duration": real_duration}


    @app_commands.command(name="list", description="Lista las playlists del servidor")
    async def list(self, interaction: discord.Interaction):
        playlists = db.list_server_playlists(interaction.guild.id)
        if not playlists:
            return await interaction.response.send_message("No hay playlists de servidor configuradas.", ephemeral=True)
        
        txt = "**📢 Playlists del Servidor:**\n"
        for name, date, creator_id in playlists:
            txt += f"- **{name}**\n"
        
        await interaction.response.send_message(txt)

    @app_commands.command(name="delete", description="[Admin] Elimina una playlist del servidor")
    async def delete_pl(self, interaction: discord.Interaction, name: str):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Solo administradores.", ephemeral=True)
            
        success, msg = db.delete_server_playlist(name, interaction.guild.id)
        await interaction.response.send_message(msg)

# Añadir el grupo al árbol
bot.tree.add_command(ServerPlaylistGroup(name="serverplaylist", description="Gestión de playlists del servidor"))


@bot.tree.command(name="myplaylists", description="Muestra tus playlists guardadas")
async def myplaylists(interaction: discord.Interaction):
    # Pasamos user_id
    playlists = db.list_playlists(interaction.guild.id, interaction.user.id)
    if not playlists:
        return await interaction.response.send_message("No tienes playlists guardadas.", ephemeral=True)
    
    txt = "**Tus Playlists:**\n"
    for name, date in playlists:
        txt += f"- **{name}** ({date})\n"
    
    await interaction.response.send_message(txt)

@bot.tree.command(name="delete", description="Elimina una playlist guardada")
@app_commands.describe(name="Nombre de la playlist a borrar")
async def delete_playlist(interaction: discord.Interaction, name: str):
    success, msg = db.delete_playlist(name, interaction.guild.id, interaction.user.id)
    await interaction.response.send_message(msg, ephemeral=True)


# CONFIGURACIÓN Y RESTRICCIONES

@bot.tree.command(name="setup", description="Configura este canal como exclusivo para música (solo enlaces)")
async def setup(interaction: discord.Interaction):
    # Verificación por ID de Discord (desde .env)
    is_admin = False
    
    # 1. Chequeo por ID directa (.env)
    if ADMIN_ID:
        # Soportar múltiples IDs separados por comas
        allowed_ids = [x.strip() for x in ADMIN_ID.split(',')]
        if str(interaction.user.id) in allowed_ids:
            is_admin = True
            
    # 2. Fallback: Si no hay .env, usar permisos de admin del servidor? 
    # El usuario dijo "que los coja de .env". Si está definido, ES la regla.
    # Si NO está definido, ¿bloqueamos todo o permitimos admin standard?
    # Asumiré: Si hay ADMIN_ID, SOLO eso cuenta. Si no, Admin del server.
    
    if not is_admin:
        if not ADMIN_ID and interaction.user.guild_permissions.administrator:
            # Si no configuraron .env, dejamos pasar a admins reales por seguridad para no brickear
            is_admin = True
        else:
             # Si hay ADMIN_ID configurado y no coincide, o no es admin
             return await interaction.response.send_message("❌ No tienes permiso para usar este comando (ID no autorizada).", ephemeral=True)
    
    success = db.set_config(interaction.guild.id, "music_channel_id", interaction.channel.id)
    if success:
        # Actualizar caché local se podría hacer aqui, pero lo haremos en on_message al consultar
        await interaction.response.send_message(f"✅ Canal **#{interaction.channel.name}** configurado como canal de música.\n⚠️ **Solo se permitirán enlaces** a partir de ahora (borraré lo demás).")
    else:
        await interaction.response.send_message("❌ Error al guardar configuración.", ephemeral=True)

# Cache simple para no matar la DB
guild_configs_cache = {}
# Cache para evitar spam de alertas (guild_id -> last_warning_time)
warning_cooldowns = {}

@bot.event
async def on_message(message):
    if message.author.bot: return
    if not message.guild: return # Ignorar DMs

    # 🥚 Easter Egg: Alberto Gay Meter
    c_lower = message.content.lower()
    if "alberto" in c_lower and ("gay" in c_lower or "gey" in c_lower) and "cuanto" in c_lower:
        # Intentar buscar al usuario para mencionarlo de verdad
        target_name = "albertmax625"
        member = discord.utils.get(message.guild.members, name=target_name)
        # Si no lo encuentra por username exacto, busca por nick o conteniendo el nombre
        if not member:
            member = discord.utils.find(lambda m: target_name in m.name.lower() or (m.nick and target_name in m.nick.lower()), message.guild.members)
            
        mention_text = member.mention if member else "@albertmax625"
        
        await message.channel.send(f"{mention_text} es 100% gay 🏳️‍🌈 Esto no tiene cura lo siento", delete_after=5)
        try: await message.delete(delay=5)
        except: pass
        return

    # Verificar si es canal restringido
    guild_id = message.guild.id
    
    # Cache hit?
    if guild_id not in guild_configs_cache:
        conf = db.get_config(guild_id)
        if conf:
            guild_configs_cache[guild_id] = conf["music_channel_id"]
        else:
            guild_configs_cache[guild_id] = None # No configurado
            
    target_channel_id = guild_configs_cache.get(guild_id)
    
    if target_channel_id and message.channel.id == target_channel_id:
        # Estamos en el canal restringido
        content = message.content.lower()
        
        # Validar SOLO YouTube o Spotify
        is_valid_link = False
        valid_domains = ["youtube.com", "youtu.be", "open.spotify.com", "spotify:"]
        
        if any(domain in content for domain in valid_domains):
            is_valid_link = True
            
        if is_valid_link:
            # AUTO-PLAY: Si el enlace es válido, intentamos reproducirlo
            # Verificar si el usuario está en voz
            if message.author.voice and message.author.voice.channel:
                 # Lanzar tarea en background para no bloquear on_message
                 url = message.content # Definir URL
                 bot.loop.create_task(play_from_message(message, url))
            else:
                 await message.channel.send(f"{message.author.mention} ⚠️ Entra a un canal de voz para que pueda reproducir el enlace.", delete_after=10)
            
        else:
            # Borrar mensaje inválido
            try:
                await message.delete()
            except Exception as e:
                print(f"[ERROR] No pude borrar el mensaje: {e}")
            
            # Enviar alerta (con cooldown de 10s para no spamear)
            now = time.time()
            last_warning = warning_cooldowns.get(guild_id, 0)
            
            if now - last_warning > 10:
                try:
                    msg = await message.channel.send(f"{message.author.mention} @everyone\n⚠️ **Solo enlaces de YouTube o Spotify.** \n*(Mensajes de texto o archivos serán eliminados sin aviso)*")
                    warning_cooldowns[guild_id] = now
                    # Borrar alerta a los 5s
                    await asyncio.sleep(5)
                    await msg.delete()
                except: pass
            
            return

    await bot.process_commands(message) # Procesar comandos normales si no se borró

async def play_from_message(message, url):
    """Lógica de reproducción automática desde un mensaje (sin comando /play)"""
    try:
        channel = message.author.voice.channel
        guild = message.guild
        voice = guild.voice_client

        # Conectar si hace falta
        if voice is None:
            await channel.connect()
            voice = guild.voice_client
        elif voice.channel != channel:
             await voice.move_to(channel)

        # Inicializar cola si no existe
        if guild.id not in music_queues:
            music_queues[guild.id] = {
                "tracks": [], "index": 0, "channel": message.channel, "loop": False, "history": []
            }
        
        queue = music_queues[guild.id]
        
        # Extracción de URL (simplificada vs /play)
        # 1. SPOTIFY
        if is_spotify_url(url):
            try:
                queries = get_spotify_queries(url)
                if not queries: return await message.channel.send("❌ Enlace de Spotify vacío o inválido.", delete_after=5)

                if len(queries) == 1:
                     # Single track
                     url = f"ytsearch:{queries[0]}"
                else:
                     # Playlist
                     msg = await message.channel.send(f"🎶 Añadiendo {len(queries)} canciones de Spotify...")
                     await asyncio.sleep(2)
                     await msg.delete()
                     
                     for q in queries:
                         # Añadir objetos light a la cola
                         queue["tracks"].append({"title": q, "webpage_url": f":{q}", "duration": 0, "thumbnail": None})
                    
                     # Si no suena nada, arrancar
                     if not voice.is_playing() and not voice.is_paused():
                         if len(queue["tracks"]) == len(queries): queue["index"] = 0
                         try:
                             first = queue["tracks"][queue["index"]]
                             # Para el primero sí buscamos info completa
                             real_title, real_dur, thumb = await play_track_in_guild(guild, first)
                             await cleanup_previous_message(guild.id)
                             prog = create_progress_bar(0, real_dur)
                             embed = discord.Embed(title="🎵 Reproduciendo Spotify", description=f"**{real_title}**\n\n{prog}", color=discord.Color.green())
                             if thumb: embed.set_thumbnail(url=thumb)
                             m = await message.channel.send(embed=embed, view=PlayerView(guild.id))
                             
                             if real_dur > 0:
                                 t = bot.loop.create_task(update_message_task(m, time.time(), real_dur, real_title, voice))
                                 audio_sources[guild.id] = {"message": m, "start_time": time.time(), "task": t, "title": real_title, "url": first["webpage_url"]}
                         except Exception as e:
                             print(f"Error auto-play spotify: {e}")
                     return

            except Exception as e:
                print(f"Error spotify message: {e}")
                return

        # 2. YOUTUBE / OTROS
        # Buscar info
        stream_url, title, duration, thumbnail, webpage_url = buscar_audio(url)
        
        # Añadir a cola
        queue["tracks"].append({"title": title, "webpage_url": webpage_url, "duration": duration, "thumbnail": thumbnail})
        
        if voice.is_playing() or voice.is_paused():
            await message.channel.send(f"📝 Añadido a la cola: **{title}**", delete_after=5)
            # Borrar mensaje original (el link)
            try: await message.delete() 
            except: pass
            
        else:
            # Reproducir
            queue["index"] = len(queue["tracks"]) - 1
            real_title, real_dur, thumb = await play_track_in_guild(guild, queue["tracks"][queue["index"]])
            
            # Borrar mensaje original (el link)
            try: await message.delete() 
            except: pass
            
            await cleanup_previous_message(guild.id)
            # Recuperar URL original
            track_url = queue["tracks"][queue["index"]].get("webpage_url", "https://discord.com")
            embed = create_minimal_embed(real_title, track_url, real_dur, 0, thumb, message.author.name)
            
            m = await message.channel.send(embed=embed, view=PlayerView(guild.id))
            
            if real_dur > 0:
                 t = bot.loop.create_task(update_message_task(m, time.time(), real_dur, real_title, voice))
                 # IMPORTANTE: Guardamos track_url (original) para que la metadata salga bien
                 audio_sources[guild.id] = {"message": m, "start_time": time.time(), "task": t, "title": real_title, "url": track_url}

    except Exception as e:
        print(f"Error playing from message: {e}")
        await message.channel.send(f"❌ Error al reproducir: {e}", delete_after=10)
 
bot.run(TOKEN) # Se ejecuta el bot
