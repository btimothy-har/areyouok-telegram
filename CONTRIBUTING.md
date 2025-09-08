# CONTRIBUTING.md

Thanks for your interest in contributing to **areyouok-telegram**!

We aim to keep all on-going work documented in our GitHub Issues.

Issues tagged with a milestone are targeted for the assigned release version. Branches targeting these issues should be merged into the release branch.

All PRs into protected branches (`main` and `release-**`) must:
1) be approved by a repository collaborator with write permissions.
2) pass all CI checks (tests and code linting).
3) meet a mininum of 85% test coverage.

---

## Project Structure

This project uses a simplified mono-project src-layout structure:

- All project metadata is stored in root
- Deployed code is in `src/areyouok_telegram`
- Undeployed code: Utility scripts in `scripts/`, Tests in `tests/`
- Tests mirror the deployed folder structure, prefixed with `test_`

---

## Local Development

### Prerequisites

1. **uv**  
   We use uv as our Python package and dependency manager.
   Install uv if you don't have it already.

   [uv Installation](https://docs.astral.sh/uv/getting-started/installation/)

2. **Postgres**<br />
   You will need a working Postgres instance. There are a few alternatives that you can pick from:
   <br />a) Run a local instance using the Postgres installers: [Mac](https://postgresapp.com) or [Windows](https://www.postgresql.org/download/windows/)
   <br />b) Run a local instance using Docker/Podman.
   <br />c) A cloud hosted Postgres instance. We use [Supabase](https://supabase.com/) as our backend, so Supabase would be the best cloud pick.

3. **Telegram Bot**<br />
   Create your own Telegram bot token by talking to [@BotFather](https://t.me/botfather) on Telegram. Use the `/newbot` command.

4. **LLM API Keys**<br />
   For simplicity, we recommend simply using a single OpenRouter API Key for LLM functionality. Alternatively, you may manually specify an `OPEN_API_KEY` and `ANTHROPIC_API_KEY`.

   Note: You will need an `OPEN_API_KEY` for voice transcription and moderation capabilities, as these call OpenAI directly.

### Getting Started

1. **Clone the Repository**  
   ```
   git clone git@github.com:btimothy-har/areyouok-telegram.git
   cd areyouok-telegram
   ```

2. **Set up Workspace**  
   Sync your workspace by installing dependencies.
   ```
   uv sync
   ```

3. **Configure Environment Variables** 
   Set up a `.env` file in the root of the repository with the environment variables listed below.

   The easiest way of doing this is to copy the `.env.example` file in the root of the repository, rename it to `.env`, and change the following environment variables:
   > 
   > **TELEGRAM_BOT_TOKEN**<br />
   Insert your own Telegram bot token here, as created in the previous steps.
   >
   > **PG_CONNECTION_STRING**<br />
   The Postgres connection string to your Postgres instance, without the leading protocol. 
   e.g. `username:password@address:port/database`, omitting the leading `postgres://...`
   > 
   > **OPENROUTER_API_KEY**<br />
   If you are using provider-direct API keys, then provide **both** `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`.

### Dev Commands

Dev commands are defined in the Makefile:

- `make test`: Runs the entire test suite with coverage included.
- `make lint`: Lints the codebase, flagging errors without fixing issues.
- `make fix`: Applies any linting autofixes, if any.
- `make run`: Runs the Telegram bot locally.
- `make reset-db`: Resets the connected database instance (clears all existing data and re-creates all tables).

---

## AI Development

We primarily use [Claude Code](https://www.anthropic.com/claude-code) as our AI development tool.

We **don't** require you to use Claude Code, but we actively maintain project tooling for Claude, so you will benefit from it.

In an attempt to limit codebase bloat, we will **not** accept PRs to write tooling for other AI development tools.

### CodeRabbit
@coderabbitai is installed on this repo.

All PRs are automatically reviewed by @coderabbitai. This is **not** a blocking review.

If you have a paid plan with CodeRabbit, you may leverage other features of CodeRabbit (e.g. agentic chat, etc).
