FROM python:3.12.10

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    ffmpeg \
    libmagic1 \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.cargo/bin:${PATH}"

COPY --from=ghcr.io/astral-sh/uv:0.7.20 /uv /uvx /bin/

WORKDIR /src

COPY . .
RUN uv sync --frozen

CMD ["uv", "run", "--frozen", "-m", "areyouok_telegram.main"]
