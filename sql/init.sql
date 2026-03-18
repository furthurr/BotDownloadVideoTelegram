CREATE TABLE IF NOT EXISTS download_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    username TEXT,
    first_name TEXT,
    url TEXT NOT NULL,
    domain TEXT,
    platform TEXT,
    status TEXT NOT NULL,
    requested_message_id INTEGER,
    file_name TEXT,
    file_size_bytes INTEGER,
    temp_file_path TEXT,
    started_at TEXT,
    finished_at TEXT,
    elapsed_ms INTEGER,
    error_code TEXT,
    error_message TEXT,
    telegram_file_id TEXT,
    bot_version TEXT
);

CREATE INDEX IF NOT EXISTS idx_download_jobs_created_at ON download_jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_download_jobs_chat_id ON download_jobs(chat_id);
CREATE INDEX IF NOT EXISTS idx_download_jobs_status ON download_jobs(status);
CREATE INDEX IF NOT EXISTS idx_download_jobs_url ON download_jobs(url);
CREATE INDEX IF NOT EXISTS idx_download_jobs_chat_status_finished ON download_jobs(chat_id, status, finished_at);

CREATE TABLE IF NOT EXISTS authorized_users (
    chat_id TEXT PRIMARY KEY,
    authorized_at TEXT NOT NULL,
    username TEXT,
    access_level TEXT NOT NULL DEFAULT 'limited'
);
