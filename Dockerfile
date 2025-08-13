FROM python:3.12.10

COPY --from=ghcr.io/astral-sh/uv:0.7.20 /uv /uvx /bin/

RUN apt-get update && apt-get install -y \
    ffmpeg \
    libmagic1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ARG GITHUB_REPOSITORY
ARG GITHUB_SHA

ENV PTB_TIMEDELTA="1"
ENV GITHUB_REPOSITORY=${GITHUB_REPOSITORY}
ENV GITHUB_SHA=${GITHUB_SHA}

COPY . .
RUN uv sync --frozen

CMD ["uv", "run", "--frozen", "-m", "areyouok_telegram.main"]
