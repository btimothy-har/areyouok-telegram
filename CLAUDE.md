# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

This project uses `uv` for Python package management. All commands should be run from the project root:

- **Setup dependencies**: `make up` or `uv sync`
- **Run the application**: `make run` or `uv run -m areyouok_telegram.main`
- **Run tests (with coverage by default)**: `make test` or `uv run pytest --cov=areyouok_telegram --cov-report=term-missing .`
- **Run a single test**: `uv run pytest tests/path/to/test_file.py::TestClass::test_method`
- **Lint code**: `make lint` or `uv run ruff check . && uv run ruff format --check .`
- **Fix linting issues**: `make fix` or `uv run ruff check --fix . && uv run ruff format .`
- **Reset database**: `make reset-db` or `uv run scripts/reset_database.py`
- **Generate encryption salt**: `make generate-salt` or `uv run scripts/generate_encryption_salt.py`
- **Build container**: `make build` (uses Podman)
- **Start container**: `make start` (runs with Podman, uses `.env` file)

## Project Architecture

This is an empathic Telegram bot application with LLM integration and encrypted user data storage.

### Core Application (`src/areyouok_telegram/`)
- **`main.py`**: Entry point with uvloop event loop, Logfire logging, and data scrubbing for privacy
- **`app.py`**: Application factory creating Telegram bot with concurrent updates support
- **`config.py`**: Environment configuration loading from `.env` file (bot token, database connection, etc.)

### Data Layer (`src/areyouok_telegram/data/`)
- **SQLAlchemy models**: `users.py`, `chats.py`, `messages.py`, `updates.py`, `sessions.py`, `media.py`, `llm_usage.py`, `context.py`
- **`connection.py`**: Async PostgreSQL connection management with context managers
- Database utilities with retry logic using tenacity

### Handlers (`src/areyouok_telegram/handlers/`)
- **`globals.py`**: Global event handlers (`on_error_event`, `on_new_update`)
- **`messages.py`**: Message-specific handlers (`on_new_message`, `on_edit_message`, `on_message_react`)
- **`commands.py`**: Command handlers for bot commands
- **`media_utils.py`**: Media file handling and processing
- **`exceptions.py`**: Custom exception handling

### Encryption Layer (`src/areyouok_telegram/encryption/`)
- User key management for encrypted data storage
- Per-user encryption keys with salt generation

### LLM Integration (`src/areyouok_telegram/llms/`)
- **`chat/`**: Chat agent with multiple personalities (anchoring, celebration, exploration, witnessing)
- **`context_compression/`**: Context compression agent for managing conversation history
- **`models/`**: LLM model definitions and base classes using pydantic-ai
- **`validators/`**: Content validation including anonymizer and content checking

### Jobs (`src/areyouok_telegram/jobs/`)
- **`conversations.py`**: Conversation management jobs
- **`ping.py`**: Health check ping job
- **`data_log_warning.py`**: Data logging warning job
- Job scheduler integration with python-telegram-bot (APScheduler under the hood)

### Research Module (`src/areyouok_telegram/research/`)
- Research agents and personality scenario studies
- Experimental features and model testing

### Key Technical Details
- **python-telegram-bot** v22.3 for Telegram API integration
- **PostgreSQL** with **asyncpg** for async database operations  
- **SQLAlchemy** v2.0 for ORM with async support
- **uvloop** for enhanced async performance
- **pydantic-ai** v0.4 for LLM integration
- **Logfire** for structured logging and tracing
- **cryptography** for user data encryption
- Concurrent updates enabled for better performance
- Handler groups: global handlers (group 0), message handlers (group 1)
- Database schema is environment-specific (development/production)

### Environment Variables Required
- `TELEGRAM_BOT_TOKEN`: Bot token from BotFather
- `PG_CONNECTION_STRING`: PostgreSQL connection string
- `DEVELOPER_CHAT_ID`: Chat ID for developer notifications
- `ENV`: Environment name (defaults to "development")
- `LOGFIRE_TOKEN`: Optional Logfire token for production logging
- `GITHUB_SHA`: Git commit SHA for deployment tracking
- `GITHUB_REPOSITORY`: GitHub repository for tracking

### Testing
- Uses **pytest** with async support (`pytest-asyncio`)
- Test coverage with **pytest-cov** (branch coverage enabled)
- **Unit tests only**: All testing focuses on individual function behavior
- All external dependencies (database, APIs, LLMs) are mocked using `unittest.mock` or `pytest-mock`
- Time-based functionality frozen during tests using **freezegun**
- Tests organized in `tests/` mirroring source structure
- **factory-boy** for generating test data
- Test fixtures best practices:
  - Shared fixtures in `tests/conftest.py`
  - Suite-specific fixtures in test files
  - Use fixtures as arguments when modifying them
  - Use `@pytest.mark.usefixtures` when not modifying