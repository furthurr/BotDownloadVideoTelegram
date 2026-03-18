# AGENTS.md

## Purpose

- This repository is a private Telegram bot that downloads videos or audio with `yt-dlp`, optionally trims videos with `ffmpeg`, sends the result back through Telegram, and records activity in SQLite.
- Main runtime code lives in `app/`; SQL bootstrap lives in `sql/init.sql`.
- The repository is now intended for direct local execution on this machine.
- There are no checked-in Cursor rules in `.cursor/rules/` or `.cursorrules`.
- There is no `.github/copilot-instructions.md` file.

## Source Of Truth

- Read `README.md` first for setup and operator workflows.
- Read `docs/PROJECT_SPEC.md` second for product scope and MVP constraints.
- Read `app/config.py` before changing behavior that depends on environment variables.
- Read `app/bot.py` before changing user flows, permissions, limits, or Telegram messages.
- Read `app/downloader.py` before changing download, trim, or cleanup behavior.
- Read `app/database.py` and `sql/init.sql` before changing persistence.

## Stack

- Python 3.11+.
- Main dependencies: `python-telegram-bot`, `yt-dlp`, `python-dotenv`, `aiosqlite`.
- External runtime tools: `ffmpeg` and SQLite.
- Local paths default to `data/` and `tmp/`.

## Important Product Constraints

- Keep the bot private; authorization is based on `ALLOWED_CHAT_IDS` and passwords stored in env vars.
- Default operating limit is 50 MB; files above the limit must be rejected and deleted.
- Downloads are temporary only; always preserve cleanup behavior.
- Concurrency is intentionally limited; current behavior uses an application-level semaphore.
- User-facing bot text is in Spanish; preserve tone and language unless the product request says otherwise.

## Repository Layout

- `app/main.py`: application bootstrap, logging setup, handler registration, polling startup.
- `app/bot.py`: Telegram command handlers, authorization flow, queueing, limits, upload flow.
- `app/downloader.py`: `yt-dlp` download logic, optional MP3 conversion, ffmpeg trimming, cleanup.
- `app/database.py`: SQLite initialization, migrations, CRUD helpers for jobs and users.
- `app/config.py`: environment-driven configuration and status constants.
- `sql/init.sql`: schema for `download_jobs` and `authorized_users`.
- `data/` and `tmp/`: local runtime directories; do not treat them as source code.
- `venv/`: local environment, not project source.

## Setup And Run Commands

- Create a virtual environment: `python3 -m venv venv`
- Activate it: `source venv/bin/activate`
- Install dependencies: `pip install -r requirements.txt`
- Create env file: `cp .env.example .env`
- Create local runtime directories: `mkdir -p data tmp/files`
- Run locally: `python app/main.py`

## Lint, Validation, And Test Reality

- There is no configured linter in the repository right now.
- There is no checked-in automated test suite in the repository right now.
- There is no `pyproject.toml`, `pytest.ini`, `ruff.toml`, `mypy.ini`, or `Makefile` at the repo root.
- Prefer lightweight validation and avoid claiming non-existent commands are part of the project.

## Practical Validation Commands

- Syntax-check all app modules: `python -m compileall app`
- Smoke-run the entrypoint locally: `python app/main.py`
- Inspect SQLite schema manually when needed: `sqlite3 data/bot.db ".schema"`

## Single-Test Guidance

- There is currently no project test file to run individually.
- If you add pytest-based tests in the future, prefer these forms:
- Run one file: `python -m pytest tests/test_bot.py`
- Run one test case: `python -m pytest tests/test_bot.py -k test_name`
- Run one node id: `python -m pytest tests/test_bot.py::test_name`
- If you introduce tests, update this file with the real command set.

## Search And Edit Guidance For Agents

- Ignore `venv/` when searching for code or tests.
- Treat `README.md` and `docs/PROJECT_SPEC.md` as behavioral references, not strict code style authorities.
- Do not edit `.env`; edit `.env.example` only when new config keys are added.
- Keep local execution working on macOS/Linux without assuming containerized paths.

## Code Style: General

- Follow existing Python style in the repo: straightforward functions, small modules, minimal indirection.
- Use 4-space indentation and standard PEP 8 spacing.
- Keep modules focused on a single responsibility.
- Favor explicit code over clever one-liners.
- Do not add comments for obvious code; only clarify non-obvious logic or invariants.

## Imports

- Group imports in this order: standard library, third-party, local `app` imports.
- Prefer explicit imports; do not use wildcard imports.
- Preserve existing module entrypoint style where `from app import config, database, bot` is already used.

## Formatting

- Match the surrounding file's quoting and formatting style instead of reformatting unrelated code.
- Keep lines reasonably readable; avoid wrapping that makes simple statements harder to scan.
- Preserve blank-line structure around top-level constants, helpers, and handlers.
- Keep SQL strings readable; multiline SQL is acceptable when it improves clarity.

## Types

- Add type hints to new helpers and non-trivial functions.
- Keep using built-in generics like `dict[str, Any]`, `tuple[str, str]`, and `int | None`.
- Avoid introducing heavy typing abstractions or protocols unless they clearly help.
- Do not over-model Telegram objects; rely on library types and runtime guards.

## Naming

- Use `snake_case` for functions, variables, and module-level helpers.
- Use `UPPER_SNAKE_CASE` for configuration values and status constants.
- Exception classes use `PascalCase`; current pattern is `DownloadError`.
- Align new names with existing domain terms: `job`, `chat_id`, `access_level`, `pending_download`, `status`.

## Async And Control Flow

- Telegram handlers are async; keep I/O paths async where practical.
- If you must call blocking libraries, isolate them behind `run_in_executor` as done in `app/downloader.py`.
- Preserve cleanup in `finally` blocks for temporary files and pending interaction state.
- Preserve semaphore-based concurrency control unless a request explicitly changes throughput.

## Error Handling

- Catch specific exceptions before generic ones.
- Use domain-specific exceptions when behavior depends on structured error codes.
- Return generic user-facing failure messages unless exposing details is intentionally requested.
- Log unexpected exceptions with stack traces when they would help operations.
- Never skip temp-file cleanup on failure paths.

## Database And Schema Changes

- Keep schema changes additive and backwards-compatible when possible.
- Mirror schema updates in both `sql/init.sql` and any startup migration logic in `app/database.py`.
- Use SQLite-friendly SQL; avoid features that are unlikely to work across versions.

## Configuration And Secrets

- Read runtime settings from environment variables through `app/config.py`.
- Never hardcode secrets, chat IDs, passwords, or tokens.
- When adding config, update `.env.example`, `README.md`, and this file if command flow changes.
- Keep safe defaults for local development when possible, but do not weaken security-sensitive behavior.

## User-Facing Messaging

- Bot messages are currently Spanish and informal-professional; preserve that voice.
- For end-user errors, prefer actionable guidance over internal details.
- Preserve command names and interaction steps unless the task explicitly changes product UX.

## What To Avoid

- Do not search or edit inside `venv/`.
- Do not introduce new infrastructure layers, queues, or services for this MVP without a clear request.
- Do not leave downloaded files behind in `tmp/`.
- Do not replace additive migrations with destructive schema resets.
- Do not silently change operational limits like file-size caps, cooldowns, or authorization rules.

## After Making Changes

- Run `python -m compileall app` at minimum.
- Mention any commands you could not run and any missing test coverage in your final handoff.
- If you add real lint or test tooling, update this file immediately so future agents have correct instructions.
