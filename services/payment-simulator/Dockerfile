# Build context is the repository root:  docker build -f services/payment-simulator/Dockerfile .
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN useradd --create-home --uid 10001 app
WORKDIR /srv
COPY packages/common-observability /opt/packages/common-observability
COPY packages/common-auth-client /opt/packages/common-auth-client
RUN pip install /opt/packages/common-observability /opt/packages/common-auth-client
COPY services/payment-simulator/pyproject.toml /srv/pyproject.toml
COPY services/payment-simulator/app /srv/app
COPY services/payment-simulator/migrations /srv/migrations
COPY services/payment-simulator/alembic.ini /srv/alembic.ini
RUN pip install /srv
USER app
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-1}"]
