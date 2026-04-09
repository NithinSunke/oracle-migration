FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV APP_ENV=production
ENV LD_LIBRARY_PATH=/opt/oracle-tools
ENV PATH=/opt/oracle-tools:${PATH}

RUN apt-get update \
    && apt-get install -y --no-install-recommends libaio1t64 libnsl2 \
    && ln -s /usr/lib/x86_64-linux-gnu/libaio.so.1t64 /usr/lib/x86_64-linux-gnu/libaio.so.1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements /app/requirements
RUN pip install --no-cache-dir -r /app/requirements/base.txt

COPY backend /app/backend
COPY config /app/config
COPY worker /app/worker

RUN adduser --disabled-password --gecos "" appuser && chown -R appuser:appuser /app

USER appuser

CMD ["celery", "-A", "worker.celery_app:celery_app", "worker", "--loglevel=info"]
