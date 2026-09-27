FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/pf-life
COPY apps/gateway/pyproject.toml ./apps/gateway/pyproject.toml
COPY apps/gateway/app ./apps/gateway/app
COPY docs/permissions.yaml ./docs/permissions.yaml
RUN pip install --no-cache-dir ./apps/gateway
RUN useradd --create-home --uid 10001 gateway && chown -R gateway:gateway /opt/pf-life
USER gateway
WORKDIR /opt/pf-life/apps/gateway
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
