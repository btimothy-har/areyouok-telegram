# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

This project uses `uv` for Python package management. All commands should be run from the project root:

- **Setup dependencies**: `make up` or `uv sync`
- **Run the application**: `make run` or `uv run -m areyouok_telegram.main`
- **Run tests**: `make test` or `uv run pytest .`
- **Run tests with coverage**: `make test-cov` or `uv run pytest --cov=areyouok_telegram --cov-report=term-missing .`
- **Lint code**: `make lint` or `uv run ruff check . && uv run ruff format --check .`
- **Fix linting issues**: `make fix` or `uv run ruff check --fix . && uv run ruff format .`

## Project Architecture

This is a Telegram bot application with the following structure:

### Core Application (`src/areyouok_telegram/`)
- **`main.py`**: Entry point that sets up the Telegram bot with uvloop, handlers, and starts polling
- **`config.py`**: Environment configuration loading from `.env` file (bot token, database connection, etc.)
- **`lifecycle.py`**: Database setup and schema creation using SQLAlchemy

### Data Layer (`src/areyouok_telegram/data/`)
- **SQLAlchemy-based models**: `chats.py`, `messages.py`, `updates.py`, `users.py`
- **`connection.py`**: Database connection management with async support
- **`utils.py`**: Database utilities including retry logic with tenacity

### Handlers (`src/areyouok_telegram/handlers/`)
- **`globals.py`**: Global event handlers (`on_error_event`, `on_new_update`)
- **`messages.py`**: Message-specific handlers (`on_new_message`, `on_edit_message`)
- **`exceptions.py`**: Custom exception handling

### Key Technical Details
- Uses **python-telegram-bot** library for Telegram API integration
- **PostgreSQL** database with **asyncpg** for async operations
- **uvloop** for enhanced async performance
- Concurrent updates enabled for better performance
- Handler groups: global handlers (group 0), message handlers (group 1)
- Database schema is environment-specific (development/production)

### Environment Variables Required
- `TELEGRAM_BOT_TOKEN`: Bot token from BotFather
- `PG_CONNECTION_STRING`: PostgreSQL connection string
- `DEVELOPER_CHAT_ID`: Chat ID for developer notifications
- `ENV`: Environment name (defaults to "development")

### Testing
- Uses **pytest** with async support (`pytest-asyncio`)
- Test coverage with **pytest-cov**
- Includes test fixtures and factory-boy for test data generation
- Tests are organized to mirror the source structure