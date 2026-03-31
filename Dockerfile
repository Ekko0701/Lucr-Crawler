# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

WORKDIR /app

# Selenium(YahooCrawler)에 필요한 Chromium 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# 의존성을 먼저 설치하여 레이어 캐시를 활용한다.
COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# 애플리케이션 코드 복사
COPY app ./app

# non-root 사용자 생성 및 로그 디렉토리 준비
RUN groupadd -r appuser && useradd -r -g appuser -m appuser \
    && mkdir -p /var/log/lucr \
    && chown -R appuser:appuser /app /var/log/lucr

USER appuser

# 기본: RabbitMQ Consumer Worker. FastAPI 서버 실행 시 CMD를 오버라이드.
CMD ["python", "-m", "app.worker"]
