import aiosqlite
import datetime
from typing import Optional, Dict, Any

from app import config

async def init_db():
    """Initializes the SQLite database with the schema if it doesn't exist."""
    async with aiosqlite.connect(config.SQLITE_DB_PATH) as db:
        with open(config.SQL_INIT_PATH, 'r') as f:
            sql_script = f.read()
            await db.executescript(sql_script)

        cursor = await db.execute("PRAGMA table_info(authorized_users)")
        columns = await cursor.fetchall()
        column_names = {col[1] for col in columns}
        if "access_level" not in column_names:
            await db.execute(
                "ALTER TABLE authorized_users ADD COLUMN access_level TEXT NOT NULL DEFAULT 'limited'"
            )

        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_download_jobs_chat_status_finished ON download_jobs(chat_id, status, finished_at)"
        )
        await db.commit()

async def create_job(chat_id: str, username: Optional[str], first_name: Optional[str], url: str, requested_message_id: int) -> int:
    """Creates a new download job in the database and returns its ID."""
    now = datetime.datetime.utcnow().isoformat()
    async with aiosqlite.connect(config.SQLITE_DB_PATH) as db:
        cursor = await db.execute('''
            INSERT INTO download_jobs (
                created_at, updated_at, chat_id, username, first_name, url, status, requested_message_id, bot_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (now, now, chat_id, username, first_name, url, config.STATUS_PENDING, requested_message_id, config.BOT_VERSION))
        job_id = cursor.lastrowid
        await db.commit()
        return job_id

async def update_job_status(job_id: int, status: str, **kwargs):
    """Updates the status and potentially other fields of a job."""
    now = datetime.datetime.utcnow().isoformat()
    
    set_clause = "updated_at = ?, status = ?"
    values: list[Any] = [now, status]

    # Dynamically update other provided fields
    allowed_fields = [
        "file_name", "file_size_bytes", "temp_file_path", "started_at",
        "finished_at", "elapsed_ms", "error_code", "error_message", "telegram_file_id"
    ]
    
    for key, value in kwargs.items():
        if key in allowed_fields:
            set_clause += f", {key} = ?"
            values.append(value)
            
    values.append(job_id)
    
    query = f"UPDATE download_jobs SET {set_clause} WHERE id = ?"
    
    async with aiosqlite.connect(config.SQLITE_DB_PATH) as db:
        await db.execute(query, tuple(values))
        await db.commit()

async def get_job(job_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves a job by its ID."""
    async with aiosqlite.connect(config.SQLITE_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM download_jobs WHERE id = ?", (job_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def is_user_authorized(chat_id: str) -> bool:
    """Checks if a user is authorized in the database."""
    async with aiosqlite.connect(config.SQLITE_DB_PATH) as db:
        cursor = await db.execute("SELECT 1 FROM authorized_users WHERE chat_id = ?", (chat_id,))
        row = await cursor.fetchone()
        return row is not None

async def get_user_access_level(chat_id: str) -> Optional[str]:
    """Returns the user's access level (limited/root) if authorized."""
    async with aiosqlite.connect(config.SQLITE_DB_PATH) as db:
        cursor = await db.execute(
            "SELECT access_level FROM authorized_users WHERE chat_id = ?",
            (chat_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None

async def count_user_daily_sent(chat_id: str, utc_start: str, utc_end: str) -> int:
    """Counts successful downloads for a user within a UTC interval."""
    async with aiosqlite.connect(config.SQLITE_DB_PATH) as db:
        cursor = await db.execute(
            '''
            SELECT COUNT(1)
            FROM download_jobs
            WHERE chat_id = ?
              AND status = ?
              AND finished_at IS NOT NULL
              AND finished_at >= ?
              AND finished_at < ?
            ''',
            (chat_id, config.STATUS_SENT, utc_start, utc_end)
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

async def authorize_user(chat_id: str, username: Optional[str], access_level: str = "limited"):
    """Adds a user to the authorized list."""
    now = datetime.datetime.utcnow().isoformat()
    async with aiosqlite.connect(config.SQLITE_DB_PATH) as db:
        await db.execute('''
            INSERT INTO authorized_users (chat_id, authorized_at, username, access_level)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                authorized_at = excluded.authorized_at,
                username = excluded.username,
                access_level = excluded.access_level
        ''', (chat_id, now, username, access_level))
        await db.commit()
