import mysql.connector # Librería para conectar con MySQL/MariaDB
import os
from dotenv import load_dotenv

load_dotenv() # Cargar variables del .env

# Configuración de conexión desde el archivo .env
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "bot_musica")

def get_connection():
    """
    Crea y devuelve una conexión a la base de datos MySQL.
    """
    try:
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        return connection
    except mysql.connector.Error as err:
        print(f"Error de conexión a la BD: {err}")
        return None

def init_db():
    """
    Inicializa la base de datos.
    Crea la base de datos y las tablas si no existen.
    """
    # Primero conectamos SIN especificar base de datos para crearla si no existe
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cursor = conn.cursor()
        
        # Crear base de datos si no existe
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
        print(f"Base de datos checked/created: {DB_NAME}")
        
        conn.close() # Cerramos conexión inicial
        
        # Ahora conectamos a la base de datos correcta
        conn = get_connection()
        if not conn:
            return

        cursor = conn.cursor()
        
        # Crear tabla de playlists
        # AUTO_INCREMENT se usa en MySQL en lugar de AUTOINCREMENT
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS playlists (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(name, guild_id, user_id)
            )
        ''')
        
        # Intentar actualizar la constraint si ya existe la tabla (migración simple)
        # Esto es un hack rápido para dev: si falla, no pasa nada, asumimos que está bien o el usuario borrará la DB
        try:
             cursor.execute("ALTER TABLE playlists DROP INDEX name")
             cursor.execute("CREATE UNIQUE INDEX name_guild_user ON playlists(name, guild_id, user_id)")
        except:
             pass 

        
        # Crear tabla de favoritos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS favorites (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                title VARCHAR(255) NOT NULL,
                url TEXT NOT NULL,
                thumbnail TEXT,
                duration INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, url(255))
            )
        ''')

        # Crear tabla de playlist_songs
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS playlist_songs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                playlist_id INT NOT NULL,
                title VARCHAR(255) NOT NULL,
                url TEXT NOT NULL,
                song_order INT NOT NULL,
                FOREIGN KEY (playlist_id) REFERENCES playlists (id) ON DELETE CASCADE
            )
        ''')
        
        # Crear tabla de configuración (para guardar canal de música, etc)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id BIGINT PRIMARY KEY,
                music_channel_id BIGINT
            )
        ''')

        # Crear tabla de playlists de servidor (Globales por guild)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS server_playlists (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                guild_id BIGINT NOT NULL,
                created_by BIGINT, -- ID del admin que la creó
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(name, guild_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS server_playlist_songs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                playlist_id INT NOT NULL,
                title VARCHAR(255) NOT NULL,
                url TEXT NOT NULL,
                song_order INT NOT NULL,
                FOREIGN KEY (playlist_id) REFERENCES server_playlists (id) ON DELETE CASCADE
            )
        ''')

        conn.commit()
        conn.close()
        print("Base de datos inicializada correctamente.")
        
    except mysql.connector.Error as err:
        print(f"Error al inicializar la BD: {err}")

# ... (Existing configs functions) ...

# === FUNCIONES DE SERVER PLAYLISTS ===

def save_server_playlist(name: str, guild_id: int, creator_id: int, tracks: list):
    """Guarda/Sobrescribe una playlist de servidor."""
    conn = get_connection()
    if not conn: return False, "Error de conexión."
    cursor = conn.cursor()
    try:
        # Upsert playlist
        cursor.execute("SELECT id FROM server_playlists WHERE name = %s AND guild_id = %s", (name, guild_id))
        row = cursor.fetchone()
        
        if row:
            playlist_id = row[0]
            # Limpiar canciones viejas
            cursor.execute("DELETE FROM server_playlist_songs WHERE playlist_id = %s", (playlist_id,))
            # Actualizar creador/fecha
            cursor.execute("UPDATE server_playlists SET created_by = %s, created_at = CURRENT_TIMESTAMP WHERE id = %s", (creator_id, playlist_id))
        else:
            cursor.execute("INSERT INTO server_playlists (name, guild_id, created_by) VALUES (%s, %s, %s)", (name, guild_id, creator_id))
            playlist_id = cursor.lastrowid
            
        # Insertar canciones
        values = [(playlist_id, t["title"], t["webpage_url"], i) for i, t in enumerate(tracks)]
        if values:
            cursor.executemany("INSERT INTO server_playlist_songs (playlist_id, title, url, song_order) VALUES (%s, %s, %s, %s)", values)
            
        conn.commit()
        return True, f"Playlist de servidor '{name}' guardada ({len(tracks)} canciones)."
    except mysql.connector.Error as err:
        conn.rollback()
        return False, str(err)
    finally:
        conn.close()

def get_server_playlist(name: str, guild_id: int):
    """Obtiene tracks de una playlist de servidor."""
    conn = get_connection()
    if not conn: return None
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM server_playlists WHERE name = %s AND guild_id = %s", (name, guild_id))
        row = cursor.fetchone()
        if not row: return None
        
        playlist_id = row[0]
        cursor.execute("SELECT title, url FROM server_playlist_songs WHERE playlist_id = %s ORDER BY song_order", (playlist_id,))
        return [{"title": r[0], "webpage_url": r[1]} for r in cursor.fetchall()]
    finally:
        conn.close()

def list_server_playlists(guild_id: int):
    """Lista nombre y creador de playlists de servidor."""
    conn = get_connection()
    if not conn: return []
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name, created_at, created_by FROM server_playlists WHERE guild_id = %s", (guild_id,))
        return cursor.fetchall()
    finally:
        conn.close()

def delete_server_playlist(name: str, guild_id: int):
    """Borra playlist de servidor."""
    conn = get_connection()
    if not conn: return False, "Error conexión."
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM server_playlists WHERE name = %s AND guild_id = %s", (name, guild_id))
        conn.commit()
        if cursor.rowcount > 0: return True, f"Playlist de servidor '{name}' eliminada."
        return False, "No existe esa playlist de servidor."
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def set_config(guild_id, key, value):
    """Guarda configuración (key=column name)."""
    # Por ahora solo soportamos music_channel_id
    if key != "music_channel_id": return False
    
    conn = get_connection()
    if not conn: return False
    
    cursor = conn.cursor()
    try:
        # Upsert
        cursor.execute(f'''
            INSERT INTO guild_config (guild_id, {key}) 
            VALUES (%s, %s) 
            ON DUPLICATE KEY UPDATE {key}=%s
        ''', (guild_id, value, value))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False
    finally:
        conn.close()

def get_config(guild_id):
    """Devuelve dict con config del server."""
    conn = get_connection()
    if not conn: return None
    
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM guild_config WHERE guild_id = %s", (guild_id,))
        return cursor.fetchone()
    except Exception as e:
        print(f"Error fetching config: {e}")
        return None
    finally:
        conn.close()

def check_playlist_exists(name: str, guild_id: int, user_id: int):
    """Devuelve el ID de la playlist si existe para ese usuario, o None."""
    conn = get_connection()
    if not conn: return None
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM playlists WHERE name = %s AND guild_id = %s AND user_id = %s", (name, guild_id, user_id))
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        conn.close()

def save_playlist(name: str, guild_id: int, user_id: int, tracks: list):
    """
    Sobrescribe una playlist existente o crea una nueva.
    """
    conn = get_connection()
    if not conn:
        return False, "Error de conexión con la base de datos."
        
    cursor = conn.cursor()
    
    try:
        # 1. Comprobar si existe la playlist PARA ESTE USUARIO
        cursor.execute("SELECT id FROM playlists WHERE name = %s AND guild_id = %s AND user_id = %s", (name, guild_id, user_id))
        row = cursor.fetchone()
        
        if row:
            playlist_id = row[0]
            # Sobrescribir: borramos canciones viejas
            cursor.execute("DELETE FROM playlist_songs WHERE playlist_id = %s", (playlist_id,))
            cursor.execute("UPDATE playlists SET created_at = CURRENT_TIMESTAMP WHERE id = %s", (playlist_id,))
        else:
            # Crear nueva
            cursor.execute("INSERT INTO playlists (name, guild_id, user_id) VALUES (%s, %s, %s)", (name, guild_id, user_id))
            playlist_id = cursor.lastrowid
        
        # 2. Insertar canciones
        values = []
        for i, track in enumerate(tracks):
            values.append((playlist_id, track["title"], track["webpage_url"], i))
            
        if values:
            cursor.executemany(
                "INSERT INTO playlist_songs (playlist_id, title, url, song_order) VALUES (%s, %s, %s, %s)",
                values
            )
        
        conn.commit()
        return True, f"Playlist '{name}' guardada correctamente ({len(tracks)} canciones)."
        
    except mysql.connector.Error as err:
        conn.rollback()
        return False, f"Error de base de datos: {err}"
    finally:
        conn.close()

def add_songs_to_playlist(name: str, guild_id: int, user_id: int, tracks: list):
    """Añade canciones al final de una playlist existente."""
    conn = get_connection()
    if not conn: return False, "Error de conexión."
    cursor = conn.cursor()
    
    try:
        # Obtener ID
        cursor.execute("SELECT id FROM playlists WHERE name = %s AND guild_id = %s AND user_id = %s", (name, guild_id, user_id))
        row = cursor.fetchone()
        if not row:
            return False, "La playlist no existe."
        playlist_id = row[0]
        
        # Obtener el último orden
        cursor.execute("SELECT MAX(song_order) FROM playlist_songs WHERE playlist_id = %s", (playlist_id,))
        max_order = cursor.fetchone()[0]
        if max_order is None: max_order = -1
        
        start_order = max_order + 1
        
        values = []
        for i, track in enumerate(tracks):
            values.append((playlist_id, track["title"], track["webpage_url"], start_order + i))
            
        if values:
            cursor.executemany(
                "INSERT INTO playlist_songs (playlist_id, title, url, song_order) VALUES (%s, %s, %s, %s)",
                values
            )
        
        conn.commit()
        return True, f"Añadidas {len(tracks)} canciones a '{name}'."
    except mysql.connector.Error as err:
        conn.rollback()
        return False, f"Error DB: {err}"
    finally:
        conn.close()


def get_playlist(name: str, guild_id: int, user_id: int):
    """
    Obtiene la lista de canciones de una playlist guardada del usuario.
    """
    conn = get_connection()
    if not conn:
        return None
        
    cursor = conn.cursor()
    
    try:
        # Buscar la playlist del usuario
        cursor.execute("SELECT id FROM playlists WHERE name = %s AND guild_id = %s AND user_id = %s", (name, guild_id, user_id))
        row = cursor.fetchone()
        
        if not row:
            return None # No existe
        
        playlist_id = row[0]
        
        # Obtener las canciones ordenadas
        cursor.execute("SELECT title, url FROM playlist_songs WHERE playlist_id = %s ORDER BY song_order", (playlist_id,))
        rows = cursor.fetchall()
        
        # Convertir al formato que usa el bot
        tracks = [{"title": r[0], "webpage_url": r[1]} for r in rows]
        return tracks
        
    finally:
        conn.close()

def list_playlists(guild_id: int, user_id: int):
    """
    Devuelve las playlists del usuario en este servidor.
    """
    conn = get_connection()
    if not conn:
        return []
        
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT name, created_at FROM playlists WHERE guild_id = %s AND user_id = %s", (guild_id, user_id))
        return cursor.fetchall()
    finally:
        conn.close()

def delete_playlist(name: str, guild_id: int, user_id: int):
    """
    Borra una playlist del usuario.
    """
    conn = get_connection()
    if not conn:
        return False, "Error de conexión."
        
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM playlists WHERE name = %s AND guild_id = %s AND user_id = %s", (name, guild_id, user_id))
        
        if cursor.rowcount > 0:
            conn.commit()
            return True, f"Playlist '{name}' eliminada."
        else:
            return False, "No se encontró esa playlist (o no es tuya)."
            
    except mysql.connector.Error as err:
        return False, f"Error: {err}"
    finally:
        conn.close()

def save_favorite(user_id: int, track: dict):
    """Guarda una canción en favoritos."""
    conn = get_connection()
    if not conn: return False, "Error DB"
    cursor = conn.cursor()
    try:
        # Usamos INSERT IGNORE para evitar duplicados sin error
        cursor.execute("""
            INSERT IGNORE INTO favorites (user_id, title, url, thumbnail, duration) 
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, track["title"], track["webpage_url"], track.get("thumbnail"), track.get("duration", 0)))
        
        conn.commit()
        if cursor.rowcount > 0:
            return True, "Canción añadida a favoritos."
        else:
            return False, "Esa canción ya estaba en tus favoritos."
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def get_favorites(user_id: int):
    """Obtiene los favoritos de un usuario."""
    conn = get_connection()
    if not conn: return []
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT title, url, duration, thumbnail FROM favorites WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
        rows = cursor.fetchall()
        return [{"title": r[0], "webpage_url": r[1], "duration": r[2], "thumbnail": r[3]} for r in rows]
    finally:
        conn.close()
