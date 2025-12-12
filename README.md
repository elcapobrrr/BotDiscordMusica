# 🎵 Tune Flow - Discord Music Bot

Bot de música avanzado para Discord con reproducción de alta calidad, playlists personalizadas, autoplay inteligente y una interfaz visual impresionante.

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![Discord.py](https://img.shields.io/badge/discord.py-2.0+-blue.svg)
![MySQL](https://img.shields.io/badge/MySQL-8.0+-orange.svg)

---

## ✨ Características Principales

### 🎧 Reproducción Multi-Plataforma
- **YouTube** - Videos, playlists y Music
- **Spotify** - Tracks, álbums y playlists (conversión automática a YouTube)
- **SoundCloud** - Soporte completo

### 🎨 Interfaz Visual Premium
- **Carátula grande** en alta calidad
- **GIF animado** de ecualizador en tiempo real
- **Barra de progreso** que se actualiza cada segundo
- **Badges dinámicos** según la fuente (Spotify, YouTube, etc.)
- **Footer con metadata** (requester, canal, autoplay status)

### 🤖 Autoplay Inteligente
- **Sin repeticiones** - Algoritmo que evita reproducir la misma canción
- **Selección aleatoria** entre 5 recomendaciones similares
- **Notificaciones temporales** que se auto-borran

### 💾 Sistema de Playlists
- **Playlists Personales** - Guarda tus propias listas
- **Playlists de Servidor** - Los admins pueden crear listas globales
- **Favoritos** - Marca canciones con ❤️ y accede rápidamente

### 🧹 Gestión Inteligente
- **Auto-limpieza de chat** - Cada 60s elimina mensajes antiguos del bot
- **Rich Presence** - Muestra la canción actual en el perfil del bot
- **Auto-desconexión** - Se desconecta tras 5 min de inactividad

### 🎛️ Controles Interactivos
Panel de botones completo:
- ⏮️ Anterior
- ⏯️ Pausa/Play
- ⏭️ Siguiente
- 🔀 Shuffle
- ❤️ Favorito
- 📍 Seek (ir a tiempo específico)
- ⏹️ Stop

---

## 🚀 Instalación

### Requisitos Previos

- **Python 3.10+**
- **FFmpeg** (para procesamiento de audio)
- **MySQL/MariaDB** (base de datos)

### 1. Clonar el repositorio

```bash
git clone https://github.com/tu-usuario/tune-flow-bot.git
cd tune-flow-bot
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurar variables de entorno

Crea un archivo `.env` en la raíz del proyecto:

```env
# Discord
DISCORD_TOKEN=tu_token_aqui
ADMIN_ID=tu_id_de_discord

# Base de Datos
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=
DB_NAME=bot_musica

# FFmpeg (opcional, si no está en PATH)
FFMPEG_PATH=ffmpeg

# Spotify (opcional)
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
```

### 4. Ejecutar el bot

```bash
python Main.py
```

El bot creará automáticamente las tablas de la base de datos en el primer inicio.

---

## 📖 Comandos

### 🎵 Reproducción y Control

| Comando | Descripción |
|---------|-------------|
| `/play <url>` | Reproduce música de YouTube o Spotify |
| `/playlist <url>` | Carga una playlist entera de YouTube |
| `/pause` | Pausa la canción actual |
| `/resume` | Reanuda la reproducción |
| `/stop` | Detiene y limpia la cola |
| `/join` | Une el bot a tu canal de voz |
| `/leave` | Desconecta el bot |
| `/move` | Mueve el bot sin cortar la música |

### 📜 Listas y Favoritos

| Comando | Descripción |
|---------|-------------|
| `/favorites` | Reproduce tus canciones favoritas |
| `/history` | Muestra las últimas 10 canciones |

### 💾 Playlists Personales

| Comando | Descripción |
|---------|-------------|
| `/save <nombre>` | Guarda la cola actual como playlist |
| `/load <nombre>` | Carga una playlist guardada |
| `/myplaylists` | Lista tus playlists |
| `/delete <nombre>` | Elimina una playlist |

### 📢 Playlists de Servidor (Admin)

| Comando | Descripción |
|---------|-------------|
| `/serverplaylist save <nombre>` | Guarda la cola como playlist global |
| `/serverplaylist load <nombre>` | Carga una playlist del servidor |
| `/serverplaylist list` | Lista playlists disponibles |
| `/serverplaylist delete <nombre>` | Elimina una playlist global |

### 🛡️ Configuración (Admin)

| Comando | Descripción |
|---------|-------------|
| `/setup` | Configura un canal exclusivo para música |

---

## 🛠️ Tecnologías

| Tecnología | Uso |
|------------|-----|
| **Python 3.10+** | Lenguaje principal |
| **discord.py** | API de Discord |
| **yt-dlp** | Extracción de audio de YouTube |
| **FFmpeg** | Procesamiento y streaming de audio |
| **Spotipy** | Integración con Spotify API |
| **MySQL/MariaDB** | Persistencia de datos |
| **mysql-connector-python** | Driver de base de datos |

---

## 📊 Arquitectura

### Base de Datos

El bot utiliza MySQL con las siguientes tablas:

- `playlists` - Playlists personales de usuarios
- `playlist_songs` - Canciones de playlists personales
- `server_playlists` - Playlists globales del servidor
- `server_playlist_songs` - Canciones de playlists del servidor
- `favorites` - Canciones favoritas por usuario
- `guilds` - Configuración por servidor

### Flujo de Reproducción

1. Usuario ejecuta `/play <url>`
2. Bot detecta la plataforma (YouTube/Spotify)
3. Si es Spotify, convierte a búsqueda de YouTube
4. Extrae metadata con `yt-dlp`
5. Procesa audio con `FFmpeg`
6. Reproduce en canal de voz
7. Actualiza embed visual en tiempo real

---

## ✨ Características Únicas

### 🎯 Autoplay Anti-Loop
Algoritmo inteligente que:
- Busca 5 canciones similares
- **Descarta siempre la primera** (evita repetir)
- Elige aleatoriamente entre las 4 restantes
- Garantiza variedad infinita

### 🧹 Auto-Clean
- Ejecuta cada 60 segundos
- Borra mensajes antiguos del bot
- **Preserva el reproductor activo**
- Mantiene el chat limpio automáticamente

### 📱 Rich Presence
- Muestra "🎵 Escuchando: [Canción]" en el perfil del bot
- Se actualiza en tiempo real
- Se limpia al detener la música

---

## 🎨 Capturas

*Próximamente*

---

## 🤝 Contribuciones

Las contribuciones son bienvenidas. Por favor:

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

---

## 📝 Licencia

Este proyecto está bajo la Licencia MIT.

---

## 📧 Contacto

Para preguntas o soporte, abre un issue en GitHub.

---

## 🎉 Agradecimientos

- [discord.py](https://github.com/Rapptz/discord.py) - Librería de Discord
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - Descarga de audio
- [Spotipy](https://github.com/plamere/spotipy) - Spotify API

---

**Desarrollado con ❤️ para la comunidad de Discord**
