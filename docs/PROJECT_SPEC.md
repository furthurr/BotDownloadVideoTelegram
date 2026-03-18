# Proyecto actual — Bot privado de Telegram para descargas

## 1. Objetivo actual

Mantener un bot privado de Telegram que:

- reciba URLs,
- descargue video o audio con `yt-dlp`,
- permita recorte de video con `ffmpeg`,
- envie el resultado al mismo chat,
- y registre todo en SQLite.

El bot corre localmente en modo polling.

## 2. Alcance funcional actual

### Incluye

- Bot privado con control de acceso por:
  - `ALLOWED_CHAT_IDS` (administradores), y/o
  - autorizacion por contrasena (`ACCESS_PASSWORD` / `ACCESS_ROOT_PASSWORD`).
- Flujo de descarga de video completo (URL directa).
- Flujo de audio MP3 (`/audio` o `/audio <url>`).
- Flujo de recorte de video (`/cortar` en modo guiado o con argumentos).
- Limite de tamano (`MAX_FILE_SIZE_MB`, default 50 MB).
- Limite diario para usuarios `limited` (`DAILY_DOWNLOAD_LIMIT`).
- Cooldown por usuario (`USER_DOWNLOAD_COOLDOWN_SECONDS`).
- Concurrencia controlada con semaforo (`MAX_CONCURRENT_DOWNLOADS`).
- Limpieza obligatoria de temporales por trabajo.
- Registro de jobs y usuarios autorizados en SQLite.

### No incluye

- Persistencia de archivos descargados a largo plazo.
- Compresion automatica o downgrade de calidad.
- Panel web o API publica.
- Webhooks publicos.
- Colas distribuidas (Redis, RabbitMQ, etc.).
- Almacenamiento externo (NAS/S3).

## 3. Reglas de producto vigentes

1. **Privado por defecto**: solo usuarios autorizados pueden usar el bot.
2. **Temporales efimeros**: todo archivo descargado/procesado debe eliminarse al final.
3. **Limite de tamano**: si excede `MAX_FILE_SIZE_MB`, no se envia y se elimina.
4. **Operacion local**: ejecucion local con Python; sin despliegue web obligatorio.
5. **Mensajes al usuario en espanol**.
6. **Sin exponer secretos**: token y contrasenas solo por entorno.

## 4. Arquitectura

```
Usuario Telegram
    -> Bot de Telegram
    -> app/main.py (polling)
        -> app/bot.py (flujos, permisos, limites)
        -> app/downloader.py (yt-dlp + ffmpeg + limpieza)
        -> app/database.py (SQLite)
        -> sql/init.sql (schema)
```

## 5. Stack tecnico real

- Python 3.11+
- `python-telegram-bot`
- `yt-dlp`
- `ffmpeg`
- `python-dotenv`
- `aiosqlite`

## 6. Variables de entorno reales

```env
TELEGRAM_BOT_TOKEN=
ALLOWED_CHAT_IDS=
ACCESS_PASSWORD=
ACCESS_ROOT_PASSWORD=
DAILY_DOWNLOAD_LIMIT=5
LIMIT_TIMEZONE=America/Mexico_City
USER_DOWNLOAD_COOLDOWN_SECONDS=10
MAX_CONCURRENT_DOWNLOADS=1
SQLITE_DB_PATH=data/bot.db
TEMP_DOWNLOAD_DIR=tmp/files
MAX_FILE_SIZE_MB=50
DOWNLOAD_TIMEOUT_SECONDS=300
LOG_LEVEL=INFO
BOT_NAME=telegram-video-bot
BOT_VERSION=0.1.0
```

## 7. Comandos soportados

- `/start` y `/help`: guia principal.
- `/estado`: nivel de acceso y uso diario.
- `/limite`: politica de limite diario.
- `/id`: muestra `chat_id`.
- `/audio`: activa flujo de MP3.
- `/cortar`: activa flujo de recorte.
- `/nivel` y `/subir_nivel`: solicitud para elevar a root por contrasena.
- `/cancelar`: cancela flujo pendiente.

## 8. Flujos funcionales

### 8.1 Video directo

1. Usuario envia URL.
2. Bot valida autorizacion, limite diario (si aplica) y cooldown.
3. Crea `download_job` en estado `PENDING`.
4. Entra a cola (semaforo) y cambia a `DOWNLOADING`.
5. Descarga archivo.
6. Si tamano valido, envia como `document`.
7. Marca `SENT` y guarda `telegram_file_id`.
8. Limpia temporales en `finally`.

### 8.2 Audio MP3

1. Usuario usa `/audio` o `/audio <url>`.
2. Se descarga mejor audio y se convierte a MP3.
3. Si tamano valido, envia como `audio`.
4. Registra estados y limpia temporales.

### 8.3 Recorte de video

1. Usuario usa `/cortar` (guiado) o `/cortar <url> <inicio> <fin>`.
2. Parsea tiempo en `min:seg` o segundos.
3. Descarga video y recorta con `ffmpeg -c copy`.
4. Valida tamano, envia, registra y limpia.

## 9. Estados de trabajo

- `PENDING`
- `DOWNLOADING`
- `DOWNLOADED`
- `SENT`
- `TOO_LARGE`
- `ERROR`
- `UNAUTHORIZED`

## 10. Modelo de datos actual

### Tabla `download_jobs`

Campos presentes en `sql/init.sql`:

- `id`
- `created_at`
- `updated_at`
- `chat_id`
- `username`
- `first_name`
- `url`
- `domain`
- `platform`
- `status`
- `requested_message_id`
- `file_name`
- `file_size_bytes`
- `temp_file_path`
- `started_at`
- `finished_at`
- `elapsed_ms`
- `error_code`
- `error_message`
- `telegram_file_id`
- `bot_version`

Indices activos:

- `idx_download_jobs_created_at`
- `idx_download_jobs_chat_id`
- `idx_download_jobs_status`
- `idx_download_jobs_url`
- `idx_download_jobs_chat_status_finished`

### Tabla `authorized_users`

- `chat_id` (PK)
- `authorized_at`
- `username`
- `access_level` (`limited` o `root`)

## 11. Estructura real del proyecto

```
app/
  main.py
  bot.py
  downloader.py
  database.py
  config.py
sql/
  init.sql
docs/
  PROJECT_SPEC.md
README.md
requirements.txt
.env.example
```

Nota: no hay `models.py`, `logger.py` ni `utils.py` como modulos separados.

## 12. Criterios de aceptacion vigentes

Se considera correcto si:

1. Usuario autorizado puede iniciar flujos y recibir respuesta.
2. Usuario no autorizado queda bloqueado y recibe mensaje de acceso.
3. Cada solicitud crea/actualiza un registro en SQLite.
4. El bot elimina temporales en exito y error.
5. Archivos mayores al limite no se envian y quedan como `TOO_LARGE`.
6. El limite diario aplica a usuarios `limited`, no a `root`.
7. El cooldown bloquea solicitudes demasiado seguidas.
8. Funciona en modo polling con ejecucion local.

## 13. Riesgos conocidos

- Cambios en plataformas pueden romper extraccion de `yt-dlp`.
- Contenido privado/restringido puede fallar sin cookies.
- `ffmpeg` ausente impide recorte/conversion.
- Errores de red/API de Telegram pueden afectar envio.
- El rendimiento depende del equipo local.

## 14. Fuera de alcance por ahora

- Compresion automatica.
- Reintentos inteligentes por calidad.
- Historial por comandos para usuarios finales.
- Dashboard administrativo web.
- Cola distribuida y workers externos.

## 15. Validacion operativa recomendada

```bash
python -m compileall app
python app/main.py
sqlite3 data/bot.db ".schema"
```
