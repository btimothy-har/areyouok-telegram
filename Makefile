up:
	uv sync

test:
	uv run pytest --cov=areyouok_telegram --cov-report=term-missing .

lint:
	uv run ruff check . && uv run ruff format --check .

fix:
	uv run ruff check --fix . && uv run ruff format .

run:
	uv run -m areyouok_telegram.main

build:
	podman build --progress=plain -t areyouok-telegram:latest .

start:
	podman run \
		--name areyouok-telegram \
		--env-file .env \
		--restart unless-stopped \
		areyouok-telegram:latest