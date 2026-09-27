# Build context is the repository root:  docker build -f services/intelligence-service/Dockerfile .
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN useradd --create-home --uid 10001 app
WORKDIR /srv
COPY packages/common-observability /opt/packages/common-observability
COPY packages/common-auth-client /opt/packages/common-auth-client
COPY packages/common-persistence /opt/packages/common-persistence
RUN pip install /opt/packages/common-observability /opt/packages/common-auth-client /opt/packages/common-persistence
COPY services/intelligence-service/pyproject.toml /srv/pyproject.toml
COPY services/intelligence-service/app /srv/app
COPY services/intelligence-service/migrations /srv/migrations
COPY services/intelligence-service/alembic.ini /srv/alembic.ini
COPY config/ai-corpus /srv/ai-corpus
RUN pip install /srv
COPY scripts/seed /srv/seed
USER app
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-1}"]
