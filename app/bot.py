import logging
import re
import datetime
import os
import math
import time
import asyncio
import unicodedata
from zoneinfo import ZoneInfo
from telegram import Update
from telegram.ext import ContextTypes, ApplicationHandlerStop

from app import config, database, downloader

logger = logging.getLogger(__name__)

# Basic URL regex
URL_REGEX = re.compile(r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+")
SECONDS_ONLY_REGEX = re.compile(r"^\d{1,4}$")


def clear_pending_download(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("pending_download", None)


def parse_mmss_to_seconds(raw_value: str) -> int | None:
    value = raw_value.strip()

    if ":" in value:
        if value.count(":") != 1:
            return None
        minutes_raw, seconds_raw = value.split(":", 1)
        if not minutes_raw.isdigit() or not seconds_raw.isdigit():
            return None
        minutes = int(minutes_raw)
        seconds = int(seconds_raw)
        if seconds > 59:
            return None
        return minutes * 60 + seconds

    if SECONDS_ONLY_REGEX.fullmatch(value):
        return int(value)

    return None


def build_request_data(update: Update, url: str) -> dict:
    return {
        "url": url,
        "chat_id": str(update.effective_chat.id),
        "username": update.effective_user.username,
        "first_name": update.effective_user.first_name,
        "message_id": update.message.message_id,
    }


def normalize_secret(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().strip()


def get_daily_utc_window_iso() -> tuple[str, str]:
    tz = ZoneInfo(config.LIMIT_TIMEZONE)
    now_local = datetime.datetime.now(datetime.timezone.utc).astimezone(tz)
    start_local = datetime.datetime.combine(now_local.date(), datetime.time.min, tzinfo=tz)
    end_local = start_local + datetime.timedelta(days=1)
    start_utc_iso = start_local.astimezone(datetime.timezone.utc).replace(tzinfo=None).isoformat()
    end_utc_iso = end_local.astimezone(datetime.timezone.utc).replace(tzinfo=None).isoformat()
    return start_utc_iso, end_utc_iso


async def enforce_download_cooldown(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: str,
) -> bool:
    cooldown_seconds = config.USER_DOWNLOAD_COOLDOWN_SECONDS
    if cooldown_seconds <= 0:
        return True

    cooldowns = context.application.bot_data.setdefault("user_download_cooldowns", {})
    now = time.monotonic()
    next_allowed_at = float(cooldowns.get(chat_id, 0.0))

    if now < next_allowed_at:
        wait_seconds = max(math.ceil(next_allowed_at - now), 1)
        if update.message:
            await update.message.reply_text(
                f"Espera {wait_seconds} segundos antes de enviar otra solicitud."
            )
        return False

    cooldowns[chat_id] = now + cooldown_seconds
    return True


async def get_sent_today(chat_id: str) -> int:
    utc_start_iso, utc_end_iso = get_daily_utc_window_iso()
    return await database.count_user_daily_sent(chat_id, utc_start_iso, utc_end_iso)


def get_download_semaphore(context: ContextTypes.DEFAULT_TYPE) -> asyncio.Semaphore:
    configured = max(config.MAX_CONCURRENT_DOWNLOADS, 1)
    semaphore = context.application.bot_data.get("download_semaphore")
    if semaphore is None:
        semaphore = asyncio.Semaphore(configured)
        context.application.bot_data["download_semaphore"] = semaphore
        context.application.bot_data["download_semaphore_limit"] = configured
        return semaphore

    current_limit = context.application.bot_data.get("download_semaphore_limit")
    if current_limit != configured:
        semaphore = asyncio.Semaphore(configured)
        context.application.bot_data["download_semaphore"] = semaphore
        context.application.bot_data["download_semaphore_limit"] = configured

    return semaphore


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /estado command."""
    if not update.effective_chat or not update.message:
        return

    chat_id_int = update.effective_chat.id
    chat_id = str(chat_id_int)
    sent_today = await get_sent_today(chat_id)

    if chat_id_int in config.ALLOWED_CHAT_IDS:
        await update.message.reply_text(
            "Estado de tu cuenta:\n"
            "Nivel: root (administrador).\n"
            f"Descargas enviadas hoy: {sent_today}.\n"
            "Límite diario: sin límite."
        )
        return

    access_level = await database.get_user_access_level(chat_id)
    if not access_level:
        await update.message.reply_text(
            "Aún no tienes acceso autorizado.\n"
            "Envíame la contraseña para activar tu cuenta."
        )
        return

    if access_level == "root":
        await update.message.reply_text(
            "Estado de tu cuenta:\n"
            "Nivel: root.\n"
            f"Descargas enviadas hoy: {sent_today}.\n"
            "Límite diario: sin límite."
        )
        return

    remaining_today = max(config.DAILY_DOWNLOAD_LIMIT - sent_today, 0)
    await update.message.reply_text(
        "Estado de tu cuenta:\n"
        "Nivel: limitado.\n"
        f"Descargas enviadas hoy: {sent_today}/{config.DAILY_DOWNLOAD_LIMIT}.\n"
        f"Descargas disponibles hoy: {remaining_today}.\n"
        f"Reinicio de límite: 00:00 ({config.LIMIT_TIMEZONE})."
    )


async def limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /limite command."""
    if not update.effective_chat or not update.message:
        return

    chat_id_int = update.effective_chat.id
    chat_id = str(chat_id_int)

    if chat_id_int in config.ALLOWED_CHAT_IDS:
        await update.message.reply_text("Tu cuenta no tiene límite diario por ser administrador.")
        return

    access_level = await database.get_user_access_level(chat_id)
    if access_level == "root":
        await update.message.reply_text("Tu cuenta no tiene límite diario (acceso root).")
        return

    sent_today = await get_sent_today(chat_id)
    remaining_today = max(config.DAILY_DOWNLOAD_LIMIT - sent_today, 0)
    await update.message.reply_text(
        "Política de límite diario:\n"
        f"Máximo: {config.DAILY_DOWNLOAD_LIMIT} archivos por día para acceso normal.\n"
        f"Reinicio: 00:00 ({config.LIMIT_TIMEZONE}).\n"
        f"Uso hoy: {sent_today}/{config.DAILY_DOWNLOAD_LIMIT}.\n"
        f"Disponibles hoy: {remaining_today}."
    )


async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /id command."""
    if not update.effective_chat or not update.message:
        return

    await update.message.reply_text(f"Tu chat_id es: {update.effective_chat.id}")

async def check_whitelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Middleware-like handler to block unauthorized users."""
    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id is None:
        raise ApplicationHandlerStop()

    chat_id_str = str(chat_id)

    if update.message and update.message.text:
        command = update.message.text.strip().split()[0].lower()
        if command in {"/start", "/help", "/estado", "/limite", "/id"}:
            return
    
    # 1. First, check if user is in the hardcoded allowed list (owner)
    if chat_id in config.ALLOWED_CHAT_IDS:
        return
        
    # 2. Check if the user is authorized in the database
    access_level = await database.get_user_access_level(chat_id_str)
    if access_level:
        return
        
    # 3. If it's a message, check if it's the password
    if update.message and update.message.text:
        normalized_text = normalize_secret(update.message.text)
        normalized_root_password = normalize_secret(config.ACCESS_ROOT_PASSWORD) if config.ACCESS_ROOT_PASSWORD else None
        normalized_access_password = normalize_secret(config.ACCESS_PASSWORD) if config.ACCESS_PASSWORD else None
        
        # Prevent people from guessing if no password is set
        if normalized_root_password and normalized_text == normalized_root_password:
            username = update.effective_user.username
            await database.authorize_user(chat_id_str, username, access_level="root")
            await update.message.reply_text(
                "✅ Contraseña root correcta. Acceso sin restricciones concedido.\n"
                "Tu chat ya quedó autorizado para usar el bot.\n"
                "Ahora puedes enviarme enlaces de video."
            )
            raise ApplicationHandlerStop()

        if normalized_access_password and normalized_text == normalized_access_password:
            username = update.effective_user.username
            await database.authorize_user(chat_id_str, username, access_level="limited")
            await update.message.reply_text(
                "✅ Contraseña correcta. Acceso concedido.\n"
                "Tu chat ya quedó autorizado para usar el bot.\n"
                "Ahora puedes enviarme enlaces de video."
            )
            raise ApplicationHandlerStop()

    # Unauthorized logic
    logger.warning(f"Unauthorized access attempt from chat_id: {chat_id}")
    if update.message:
        await update.message.reply_text(
            "🔒 Este bot es privado.\n"
            "Para continuar, envíame la contraseña en un mensaje.\n"
            "Si no la conoces, solicítala a @PedroGVFurthurr."
        )
    raise ApplicationHandlerStop()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /start command."""
    await update.message.reply_text(
        "Hola. Soy un bot privado creado por @PedroGVFurthurr para descargar videos.\n\n"
        "Comandos:\n"
        "/start - Muestra esta guía de uso.\n"
        "/help - Muestra esta guía de uso.\n"
        "/estado - Muestra tu nivel y uso diario.\n"
        "/limite - Muestra tu límite diario actual.\n"
        "/id - Muestra tu chat_id.\n"
        "/audio - Activa descarga de solo audio MP3.\n"
        "/cortar - Activa modo recorte de video.\n"
        "/nivel - Subir a acceso sin límite con contraseña.\n"
        "/cancelar - Cancela la solicitud en curso.\n\n"
        "Cómo usar el bot:\n"
        "1) Si aún no tienes acceso, envíame la contraseña.\n"
        "2) Si envías una URL directamente, descargo el video completo.\n"
        "3) Usa /audio y luego URL para recibir solo MP3.\n"
        "4) Usa /cortar y te pediré URL, inicio y fin en min:seg.\n\n"
        "Si no conoces la contraseña, solicítala a @PedroGVFurthurr."
    )


async def upgrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /nivel command."""
    if not update.effective_chat or not update.message:
        return

    chat_id = update.effective_chat.id
    chat_id_str = str(chat_id)

    if chat_id in config.ALLOWED_CHAT_IDS:
        await update.message.reply_text("Ya tienes acceso sin restricciones por ser administrador.")
        return

    access_level = await database.get_user_access_level(chat_id_str)
    if access_level == "root":
        await update.message.reply_text("Ya tienes acceso sin restricciones.")
        return

    context.user_data["awaiting_root_password"] = True
    await update.message.reply_text(
        "Envíame ahora la contraseña root para subir tu nivel.\n"
        "Si no la conoces, solicítala a @PedroGVFurthurr."
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    had_pending = bool(context.user_data.get("pending_download"))
    had_root_wait = bool(context.user_data.get("awaiting_root_password"))
    clear_pending_download(context)
    context.user_data.pop("awaiting_root_password", None)

    if had_pending or had_root_wait:
        await update.message.reply_text("Solicitud cancelada.")
        return

    await update.message.reply_text("No hay ninguna solicitud en curso para cancelar.")


async def audio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    clear_pending_download(context)

    if context.args:
        url = context.args[0].strip()
        if not URL_REGEX.match(url):
            await update.message.reply_text("URL inválida. Uso: /audio <url>")
            return
        request_data = build_request_data(update, url)
        request_data["mode"] = "audio"
        await process_download_request(update, context, request_data)
        return

    context.user_data["pending_download"] = {
        "stage": "awaiting_audio_url",
        **build_request_data(update, ""),
    }
    await update.message.reply_text("Envíame la URL para descargar solo el audio en MP3.")


async def cortar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    clear_pending_download(context)

    if context.args:
        url = context.args[0].strip()
        if not URL_REGEX.match(url):
            await update.message.reply_text("URL inválida. Uso: /cortar <url> [inicio min:seg] [fin min:seg]")
            return

        request_data = build_request_data(update, url)
        request_data["mode"] = "trim"

        if len(context.args) >= 3:
            clip_start_seconds = parse_mmss_to_seconds(context.args[1].strip())
            clip_end_seconds = parse_mmss_to_seconds(context.args[2].strip())
            if clip_start_seconds is None or clip_end_seconds is None:
                await update.message.reply_text(
                    "Formato inválido. Usa min:seg (ej. 1:20 o 0:7) o segundos (ej. 7)."
                )
                return
            if clip_end_seconds <= clip_start_seconds:
                await update.message.reply_text("El tiempo de fin debe ser mayor al tiempo de inicio.")
                return
            request_data["clip_start_seconds"] = clip_start_seconds
            request_data["clip_end_seconds"] = clip_end_seconds
            await process_download_request(update, context, request_data)
            return

        context.user_data["pending_download"] = {
            "stage": "awaiting_clip_start",
            **request_data,
        }
        await update.message.reply_text(
            "Envíame el inicio del recorte en formato min:seg (ejemplo: 1:20 o 0:7). "
            "También puedes enviar solo segundos (ejemplo: 7)."
        )
        return

    context.user_data["pending_download"] = {
        "stage": "awaiting_clip_url",
        **build_request_data(update, ""),
    }
    await update.message.reply_text("Envíame la URL del video que quieres recortar.")


async def process_download_request(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    request_data: dict,
):
    if not update.message:
        return

    chat_id = request_data["chat_id"]
    username = request_data.get("username")
    first_name = request_data.get("first_name")
    url = request_data["url"]
    message_id = request_data["message_id"]
    mode = request_data.get("mode", "video")
    clip_start_seconds = request_data.get("clip_start_seconds")
    clip_end_seconds = request_data.get("clip_end_seconds")

    if update.effective_chat and update.effective_chat.id not in config.ALLOWED_CHAT_IDS:
        access_level = await database.get_user_access_level(chat_id)
        if access_level != "root":
            utc_start_iso, utc_end_iso = get_daily_utc_window_iso()
            sent_today = await database.count_user_daily_sent(chat_id, utc_start_iso, utc_end_iso)
            if sent_today >= config.DAILY_DOWNLOAD_LIMIT:
                clear_pending_download(context)
                await update.message.reply_text(
                    "Por estabilidad del sistema, solo se te permite descargar un máximo de "
                    f"{config.DAILY_DOWNLOAD_LIMIT} archivos por día. Si necesitas descargar más, "
                    "solicita a @PedroGVFurthurr que te habilite más descargas.",
                )
                return

    if not await enforce_download_cooldown(update, context, chat_id):
        clear_pending_download(context)
        return

    semaphore = get_download_semaphore(context)
    was_queued = semaphore.locked()

    job_id = await database.create_job(chat_id, username, first_name, url, message_id)
    status_msg = await update.message.reply_text(
        "Solicitud recibida. En cola, iniciará cuando termine la descarga actual..."
        if was_queued else
        "URL recibida. Iniciando descarga..."
    )

    async with semaphore:
        try:
            if was_queued:
                await status_msg.edit_text("URL recibida. Iniciando descarga...")

            await database.update_job_status(
                job_id,
                config.STATUS_DOWNLOADING,
                started_at=datetime.datetime.utcnow().isoformat(),
            )

            if mode == "audio":
                await status_msg.edit_text("Convirtiendo y preparando MP3...")
            elif mode == "trim":
                await status_msg.edit_text("Descargando y recortando video...")
            else:
                await status_msg.edit_text("Procesando archivo...")

            file_path, file_size_bytes = await downloader.download_video(
                url,
                job_id,
                audio_only=(mode == "audio"),
                clip_start_seconds=clip_start_seconds,
                clip_end_seconds=clip_end_seconds,
            )

            await database.update_job_status(
                job_id,
                config.STATUS_DOWNLOADED,
                file_name=os.path.basename(file_path),
                file_size_bytes=file_size_bytes,
                temp_file_path=file_path,
            )

            await status_msg.edit_text("Subiendo archivo a Telegram...")

            with open(file_path, "rb") as file_handle:
                if mode == "audio":
                    sent_message = await context.bot.send_audio(
                        chat_id=chat_id,
                        audio=file_handle,
                        reply_to_message_id=message_id,
                        read_timeout=config.DOWNLOAD_TIMEOUT_SECONDS,
                        write_timeout=config.DOWNLOAD_TIMEOUT_SECONDS,
                        connect_timeout=config.DOWNLOAD_TIMEOUT_SECONDS,
                        pool_timeout=config.DOWNLOAD_TIMEOUT_SECONDS,
                    )
                else:
                    sent_message = await context.bot.send_document(
                        chat_id=chat_id,
                        document=file_handle,
                        reply_to_message_id=message_id,
                        read_timeout=config.DOWNLOAD_TIMEOUT_SECONDS,
                        write_timeout=config.DOWNLOAD_TIMEOUT_SECONDS,
                        connect_timeout=config.DOWNLOAD_TIMEOUT_SECONDS,
                        pool_timeout=config.DOWNLOAD_TIMEOUT_SECONDS,
                    )

            telegram_file_id = None
            if getattr(sent_message, "audio", None):
                telegram_file_id = sent_message.audio.file_id
            elif getattr(sent_message, "document", None):
                telegram_file_id = sent_message.document.file_id

            await database.update_job_status(
                job_id,
                config.STATUS_SENT,
                finished_at=datetime.datetime.utcnow().isoformat(),
                telegram_file_id=telegram_file_id,
            )

            await status_msg.edit_text("Listo.")

        except downloader.DownloadError as e:
            logger.error(f"Download error for job {job_id}: {e.code} - {e.message}")
            if e.code == config.STATUS_TOO_LARGE:
                await database.update_job_status(
                    job_id,
                    config.STATUS_TOO_LARGE,
                    error_code=e.code,
                    error_message=e.message,
                    finished_at=datetime.datetime.utcnow().isoformat(),
                )
                await status_msg.edit_text(
                    "No se puede enviar porque el archivo excede el límite operativo de 50 MB "
                    "(característica aun en desarrollo). El archivo fue eliminado automáticamente."
                )
            else:
                await database.update_job_status(
                    job_id,
                    config.STATUS_ERROR,
                    error_code=e.code,
                    error_message=e.message,
                    finished_at=datetime.datetime.utcnow().isoformat(),
                )
                await status_msg.edit_text("No se pudo procesar la URL.")

        except Exception as e:
            logger.error(f"Unexpected error for job {job_id}: {str(e)}", exc_info=True)
            await database.update_job_status(
                job_id,
                config.STATUS_ERROR,
                error_code="UNEXPECTED_ERROR",
                error_message=str(e),
                finished_at=datetime.datetime.utcnow().isoformat(),
            )
            await status_msg.edit_text("No se pudo procesar la URL debido a un error interno.")

        finally:
            file_path_safe = locals().get("file_path")
            if file_path_safe:
                job_dir = os.path.dirname(file_path_safe)
                downloader.cleanup_job_files(job_dir)
            clear_pending_download(context)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main handler for text messages (passwords, command flows, direct URLs)."""
    if not update.message:
        return

    text = update.message.text.strip()
    chat_id = str(update.effective_chat.id)
    username = update.effective_user.username

    if context.user_data.get("awaiting_root_password"):
        context.user_data["awaiting_root_password"] = False

        normalized_text = normalize_secret(text)
        normalized_root_password = normalize_secret(config.ACCESS_ROOT_PASSWORD) if config.ACCESS_ROOT_PASSWORD else None

        if not normalized_root_password:
            await update.message.reply_text(
                "No hay una contraseña root configurada en este momento.\n"
                "Contacta a @PedroGVFurthurr."
            )
            return

        if normalized_text == normalized_root_password:
            await database.authorize_user(chat_id, username, access_level="root")
            await update.message.reply_text(
                "✅ Contraseña root correcta.\n"
                "Tu acceso ahora es sin restricciones."
            )
            return

        await update.message.reply_text(
            "❌ Contraseña root incorrecta.\n"
            "Si deseas intentarlo de nuevo, usa /nivel."
        )
        return

    pending_download = context.user_data.get("pending_download")
    if pending_download:
        stage = pending_download.get("stage")

        if stage == "awaiting_audio_url":
            if not URL_REGEX.match(text):
                await update.message.reply_text("URL inválida. Envíame una URL válida para /audio.")
                return
            pending_download.update(build_request_data(update, text))
            pending_download["mode"] = "audio"
            await process_download_request(update, context, pending_download)
            return

        if stage == "awaiting_clip_url":
            if not URL_REGEX.match(text):
                await update.message.reply_text("URL inválida. Envíame una URL válida para /cortar.")
                return
            pending_download.update(build_request_data(update, text))
            pending_download["stage"] = "awaiting_clip_start"
            pending_download["mode"] = "trim"
            await update.message.reply_text("Envíame el inicio del recorte en formato min:seg (ejemplo: 1:20).")
            return

        if stage == "awaiting_clip_start":
            clip_start_seconds = parse_mmss_to_seconds(text)
            if clip_start_seconds is None:
                await update.message.reply_text(
                    "Formato inválido. Usa min:seg (ej. 0:30 o 12:05) o segundos (ej. 7)."
                )
                return

            pending_download["clip_start_seconds"] = clip_start_seconds
            pending_download["stage"] = "awaiting_clip_end"
            await update.message.reply_text(
                "Ahora envíame el fin del recorte en formato min:seg (ejemplo: 2:45) "
                "o solo segundos (ejemplo: 165)."
            )
            return

        if stage == "awaiting_clip_end":
            clip_end_seconds = parse_mmss_to_seconds(text)
            if clip_end_seconds is None:
                await update.message.reply_text(
                    "Formato inválido. Usa min:seg (ej. 1:45 o 15:00) o segundos (ej. 7)."
                )
                return

            clip_start_seconds = pending_download.get("clip_start_seconds")
            if clip_start_seconds is None or clip_end_seconds <= clip_start_seconds:
                await update.message.reply_text(
                    "El tiempo de fin debe ser mayor al tiempo de inicio. Vuelve a enviar el fin en min:seg."
                )
                return

            pending_download["clip_end_seconds"] = clip_end_seconds
            pending_download["mode"] = "trim"
            await process_download_request(update, context, pending_download)
            return

        clear_pending_download(context)
        await update.message.reply_text("Se reinició la solicitud. Envíame nuevamente la URL.")
        return

    if not URL_REGEX.match(text):
        await update.message.reply_text("Por favor, envíame una URL válida.")
        return

    request_data = build_request_data(update, text)
    request_data["mode"] = "video"
    await process_download_request(update, context, request_data)
