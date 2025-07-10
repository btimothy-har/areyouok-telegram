up:
	uv sync

lint:
	uv run ruff check . && uv run ruff format --check .

fix:
	uv run ruff check --fix . && uv run ruff format .

run:
	uv run -m areyouok_telegram.main
