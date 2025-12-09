import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from yt_dlp import YoutubeDL
import logging

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN") # Token del bot

intents = discord.Intents.default() # Intents del bot
intents.message_content = False

bot = commands.Bot(command_prefix="!", intents=intents)

# Diccionario para guardar el source de audio por servidor
# Esto permite pausar y reanudar sin perder el source
audio_sources = {}

# Configurar logging para ver más información
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s')

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


def buscar_audio(url: str): # Busca el audio en Youtube
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

    voice = interaction.guild.voice_client # Obtiene el canal de voz del bot
    if voice.is_playing(): # Si el bot está reproduciendo, se detiene
        print("[PLAY] Deteniendo reproducción anterior") # Muestra un mensaje de que se detiene la reproducción anterior
        voice.stop() # Se detiene la reproducción anterior

    try:
        print("[PLAY] Obteniendo información del audio...")
        stream_url, title = buscar_audio(url) # Busca el audio en Youtube
    except Exception as e: # Si ocurre un error, se envía un mensaje de error
        print(f"[PLAY] ERROR al obtener audio: {e}")
        return await interaction.followup.send(f"No pude obtener el audio: {e}", ephemeral=True) # Se envía un mensaje de error

    try:
        print("[FFMPEG] Iniciando fuente de audio...") # Muestra un mensaje de que se inicia la fuente de audio
        print(f"[FFMPEG] Ejecutable: E:\\python\\Bot_Musica\\ffmpeg\\bin\\ffmpeg.exe")
        print(f"[FFMPEG] Opciones: {FFMPEG_OPTIONS}") # Muestra las opciones de FFMPEG
        
        # Intentar primero con from_probe, si falla usar FFmpegPCMAudio
        try:
            source = await discord.FFmpegOpusAudio.from_probe( # Se crea la fuente de audio con FFmpegOpusAudio.from_probe
                stream_url, 
                executable="E:\\python\\Bot_Musica\\ffmpeg\\bin\\ffmpeg.exe", # Ruta del ejecutable de FFMPEG
                **FFMPEG_OPTIONS
            )
            print("[FFMPEG] Fuente creada con FFmpegOpusAudio.from_probe") # Muestra un mensaje de que se creó la fuente de audio con FFmpegOpusAudio.from_probe
        except Exception as probe_error:
            print(f"[FFMPEG] from_probe falló: {probe_error}") # Muestra un mensaje de que from_probe falló
            print("[FFMPEG] Intentando con FFmpegPCMAudio como alternativa...")
            source = discord.FFmpegPCMAudio( # Se crea la fuente de audio con FFmpegPCMAudio
                stream_url,
                executable="E:\\python\\Bot_Musica\\ffmpeg\\bin\\ffmpeg.exe", # Ruta del ejecutable de FFMPEG
                **FFMPEG_OPTIONS
            )
            print("[FFMPEG] Fuente creada con FFmpegPCMAudio") # Muestra un mensaje de que se creó la fuente de audio con FFmpegPCMAudio
        
        print(f"[PLAY] Iniciando reproducción de: {title}") # Muestra el título de la canción que se va a reproducir
        
        # Guardar el source en el diccionario para poder pausar/reanudar
        audio_sources[interaction.guild.id] = { # Se guarda el source en el diccionario de audio_sources
            "source": source,
            "title": title, # Se guarda el título de la canción
            "url": stream_url # Se guarda la url de la canción
        } # Se guarda el source en el diccionario de audio_sources
        
        def after_playing(error): # Función para después de la reproducción
            if error:
                print(f"\n[PLAY] Reproducción finalizada con error: {error}") # Muestra un mensaje de que la reproducción finalizó con error
            else:
                print("\n[PLAY] Reproducción terminada correctamente") # Muestra un mensaje de que la reproducción terminó correctamente
            # Limpiar el source cuando termine
            if interaction.guild.id in audio_sources: # Si el servidor está en el diccionario de audio_sources, se elimina
                del audio_sources[interaction.guild.id] # Se elimina el servidor del diccionario de audio_sources
        
        voice.play(source, after=after_playing) # Se reproduce la canción
        await interaction.followup.send(f"Reproduciendo: {title}") # Se envía un mensaje de confirmación
        print(f"[PLAY] Reproducción iniciada exitosamente") # Muestra un mensaje de que la reproducción inició correctamente
        
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
                        executable="E:\\python\\Bot_Musica\\ffmpeg\\bin\\ffmpeg.exe", # Ruta del ejecutable de FFMPEG
                        **FFMPEG_OPTIONS
                    )
                except:
                    source = discord.FFmpegPCMAudio( # Se crea la fuente de audio con FFmpegPCMAudio
                        saved_data["url"],
                        executable="E:\\python\\Bot_Musica\\ffmpeg\\bin\\ffmpeg.exe", # Ruta del ejecutable de FFMPEG
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
 
bot.run(TOKEN) # Se ejecuta el bot