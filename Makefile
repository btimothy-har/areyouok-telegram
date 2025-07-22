up:
	uv sync

test:
	uv run pytest .

test-cov:
	uv run pytest --cov=areyouok_telegram --cov-report=term-missing --cov-report=html --cov-report=xml .

test-cov-fail:
	uv run pytest --cov=areyouok_telegram --cov-report=term-missing --cov-fail-under=80 .

lint:
	uv run ruff check . && uv run ruff format --check .

fix:
	uv run ruff check --fix . && uv run ruff format .

run:
	uv run -m areyouok_telegram.main
