09/12/2025 : 22:28 

# Bot de Música para Discord

Bot de música para Discord que permite reproducir audio desde YouTube en canales de voz. Desarrollado con Python, discord.py y yt-dlp.

## 📋 Características

- ✅ Reproducción de audio desde YouTube
- ✅ Comandos slash (/) para fácil uso
- ✅ Control de reproducción (play, pause, resume, stop)
- ✅ Gestión de conexión a canales de voz
- ✅ Sistema de guardado de sources para pausar/reanudar sin perder el audio
- ✅ Logging detallado para debugging
- ✅ Manejo robusto de errores con fallback automático

## 🔧 Requisitos Previos

### Software Necesario

1. **Python 3.8 o superior**
   - Descarga desde: https://www.python.org/downloads/

** OBLIGATORIO ** 
2. **FFmpeg**
   - Descarga desde: https://www.gyan.dev/ffmpeg/builds/
   - Extrae los archivos en la carpeta `ffmpeg/` del proyecto
   - El bot busca FFmpeg en: `E:\python\Bot_Musica\ffmpeg\bin\ffmpeg.exe` -- en mi caso en el tuyo en la carpeta que tu tengas el bot
   - Si tu ruta es diferente, modifica la ruta en `Main.py`

### Librerías de Python
** OBLIGATORIO ** 
Las siguientes librerías se instalan automáticamente con `requirements.txt`:

- `discord.py>=2.3.0` - Librería para interactuar con Discord
- `yt-dlp>=2023.10.0` - Extracción de audio desde YouTube
- `python-dotenv>=1.0.0` - Gestión de variables de entorno
- `PyNaCl>=1.5.0` - Requerido para audio en Discord

## 📦 Instalación

1. **Clona o descarga el proyecto**

2. **Instala las dependencias de Python:**
   ```power shell
   pip install -r requirements.txt
   ```

3. **Configura FFmpeg:**
   - Descarga FFmpeg desde el enlace anterior
   - Extrae los archivos en la carpeta `ffmpeg/` del proyecto
   - Asegúrate de que la ruta `ffmpeg/bin/ffmpeg.exe` exista ** Importante ** 

4. **Configura el token del bot:**
   - Crea un archivo `.env` en la raíz del proyecto
   - Agrega tu token de Discord:
     ```
     DISCORD_TOKEN=tu_token_aqui -- Tienes que poner el token despues del = 
     ```

## ⚙️ Configuración

### Obtener Token de Discord

1. Ve a https://discord.com/developers/applications
2. Crea una nueva aplicación o selecciona una existente
3. Ve a la sección "Bot"
4. Copia el token y pégalo en tu archivo `.env`

### Permisos del Bot

El bot necesita los siguientes permisos en tu servidor:
- ✅ Conectar (Connect)
- ✅ Hablar (Speak)
- ✅ Usar comandos de aplicación (Use Application Commands)

### Configurar el ID del Servidor

En `Main.py`, línea 66, reemplaza el `guild_id` con el ID de tu servidor:

```python
guild_id = 1375862077020831774  # Reemplaza con el ID de tu servidor de discord
```

Para obtener el ID de tu servidor:
1. Activa el modo desarrollador en Discord (Configuración > Avanzado > Modo desarrollador)
2. Click derecho en tu servidor > Copiar ID

### Cambiar la Ruta de FFmpeg

Si FFmpeg está en otra ubicación, modifica las rutas en `Main.py`:
- Línea 132: `executable="E:\\python\\Bot_Musica\\ffmpeg\\bin\\ffmpeg.exe"`
- Línea 139: `executable="E:\\python\\Bot_Musica\\ffmpeg\\bin\\ffmpeg.exe"`
- Línea 148: `executable="E:\\python\\Bot_Musica\\ffmpeg\\bin\\ffmpeg.exe"`
- Línea 216: `executable="E:\\python\\Bot_Musica\\ffmpeg\\bin\\ffmpeg.exe"`
- Línea 222: `executable="E:\\python\\Bot_Musica\\ffmpeg\\bin\\ffmpeg.exe"`

## 🚀 Uso

1. **Inicia el bot:**
   ```CMD o Power Shell
   python Main.py
   ```

2. **Invita el bot a tu servidor:**
   - Usa el enlace de invitación con los permisos necesarios
   - El bot se conectará y sincronizará los comandos

3. **Usa los comandos en Discord:**
   - Todos los comandos usan el prefijo `/` (comandos slash)

## 📝 Comandos Disponibles

### `/join`
Une el bot a tu canal de voz actual.

**Uso:** `/join`

**Requisitos:**
- Debes estar en un canal de voz
- El bot debe tener permisos para conectarse

**Ejemplo:**
```
/join
```

---

### `/leave`
Desconecta el bot del canal de voz.

**Uso:** `/leave`

**Ejemplo:**
```
/leave
```

---

### `/play`
Reproduce música desde YouTube.

**Uso:** `/play url:<URL_de_YouTube>`

**Parámetros:**
- `url` (requerido): URL del video de YouTube

**Requisitos:**
- Debes estar en un canal de voz
- El bot se conectará automáticamente si no está conectado

**Ejemplo:**
```
/play url:https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

**Notas:**
- Si hay una reproducción en curso, se detendrá y comenzará la nueva
- El bot guarda el source para permitir pausar/reanudar
- Muestra información detallada en la consola

---

### `/pause`
Pausa la reproducción actual.

**Uso:** `/pause`

**Requisitos:**
- El bot debe estar reproduciendo audio

**Ejemplo:**
```
/pause
```

**Notas:**
- El audio se pausa pero no se pierde
- Puedes reanudar con `/resume`

---

### `/resume`
Reanuda la reproducción pausada.

**Uso:** `/resume`

**Requisitos:**
- El bot debe tener audio pausado o guardado

**Ejemplo:**
```
/resume
```

**Notas:**
- Si el source se perdió, intenta recrearlo automáticamente
- Funciona incluso si el bot se desconectó y reconectó

---

### `/stop`
Detiene completamente la reproducción.

**Uso:** `/stop`

**Requisitos:**
- El bot debe estar reproduciendo o pausado

**Ejemplo:**
```
/stop
```

**Notas:**
- Elimina el source guardado
- Para reproducir de nuevo, usa `/play`

## 🏗️ Estructura del Código

### Archivos Principales

- `Main.py` - Archivo principal con toda la lógica del bot
- `requirements.txt` - Dependencias del proyecto
- `.env` - Variables de entorno (crear manualmente)
- `ffmpeg/` - Carpeta con los binarios de FFmpeg

### Componentes Principales

#### Variables Globales

- `audio_sources`: Diccionario que guarda los sources de audio por servidor
- `YDL_OPTIONS`: Configuración para yt-dlp
- `FFMPEG_OPTIONS`: Opciones para FFmpeg

#### Funciones

- `buscar_audio(url)`: Extrae información y URL del audio desde YouTube
- `on_ready()`: Evento que se ejecuta cuando el bot está listo
- Comandos slash: `/join`, `/leave`, `/play`, `/pause`, `/resume`, `/stop`

## 🔍 Logging y Debugging

El bot incluye logging detallado que muestra:

- Información de conexión del bot
- Sincronización de comandos
- Procesos de reproducción (play, pause, resume, stop)
- Información de yt-dlp (título, duración, URL)
- Procesos de FFmpeg
- Errores y excepciones

**Ejemplo de salida en consola:**
```
[PLAY] Comando ejecutado por: Usuario
[PLAY] URL recibida: https://www.youtube.com/watch?v=...
[YT-DLP] Buscando audio para: https://www.youtube.com/watch?v=...
[YT-DLP] Título: Nombre del Video
[YT-DLP] Duración: 180s
[FFMPEG] Iniciando fuente de audio...
[PLAY] Reproducción iniciada exitosamente
```

## ⚠️ Solución de Problemas

### Error: "No supported JavaScript runtime could be found"

**Problema:** Advertencia de yt-dlp sobre runtime de JavaScript.

**Solución:** 
- Esta es solo una advertencia, no un error crítico
- El bot funcionará normalmente
- Para eliminarla, instala Node.js (opcional)

### Error: "Probe 'native' using 'ffmpeg.exe' failed"

**Problema:** FFmpeg no puede analizar el stream.

**Solución:**
- El bot tiene un fallback automático a `FFmpegPCMAudio`
- Verifica que FFmpeg esté en la ruta correcta
- Asegúrate de que el archivo `ffmpeg.exe` existe

### Error: "No estoy en un canal de voz"

**Problema:** El bot no está conectado a un canal.

**Solución:**
- Usa `/join` para conectar el bot
- O usa `/play` que conecta automáticamente

### El bot no responde a los comandos

**Problema:** Los comandos slash no están sincronizados.

**Solución:**
- Espera unos minutos después de iniciar el bot
- Los comandos se sincronizan automáticamente
- Verifica que el bot tenga permisos en el servidor

### No se puede pausar/reanudar

**Problema:** El source se pierde al pausar.

**Solución:**
- El código actual guarda el source automáticamente
- Si persiste, verifica los logs en consola
- El bot intenta recrear el source si se pierde

### Error de conexión a YouTube

**Problema:** No se puede obtener el audio.

**Solución:**
- Verifica tu conexión a internet
- La URL puede ser inválida o el video puede estar restringido
- Algunos videos pueden requerir autenticación

## 🔐 Seguridad

- **Nunca compartas tu token de Discord**
- Mantén el archivo `.env` en `.gitignore`
- No subas el token a repositorios públicos

## 📄 Licencia

Este proyecto es de código abierto. Úsalo y modifícalo libremente.

## 🤝 Contribuciones

Las contribuciones son bienvenidas. Si encuentras un bug o tienes una sugerencia, no dudes en reportarlo.

## 📞 Soporte

Si tienes problemas:
1. Revisa la sección de solución de problemas
2. Verifica los logs en la consola
3. Asegúrate de tener todas las dependencias instaladas

---

**Desarrollado con ❤️ usando Python y discord.py Capobrr**
