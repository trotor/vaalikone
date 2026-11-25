FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r app && useradd -r -g app -d /app -s /usr/sbin/nologin app

COPY pyproject.toml .
COPY src/ src/
COPY config/ config/
COPY alembic/ alembic/
COPY alembic.ini .

RUN pip install --no-cache-dir . && chown -R app:app /app

USER app

EXPOSE 8003

CMD ["uvicorn", "vaalikone.api.app:app", "--host", "0.0.0.0", "--port", "8003"]
