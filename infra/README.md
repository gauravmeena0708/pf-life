# Running the EPFO POC locally

**SYNTHETIC DEMONSTRATION — NOT AN OFFICIAL EPFO SYSTEM.** Every credential here is development-only.

## Start

```bash
make up          # creates .env from .env.example on first run, builds and starts everything
make migrate     # standard tables in every service database
make demo        # prints URLs and personas
```

Needs Docker with the Compose v2 plugin (`docker compose version`). On Ubuntu: `sudo apt-get install -y docker-compose-v2`.

| Mode | Command | Notes |
|---|---|---|
| Full | `make up` | ~3 GB RAM |
| Lite | `make up-lite` | one worker, small pools (~2 GB) |
| Debug | `make up-direct` | also publishes each service on 127.0.0.1:8101–8111 |
| AI | `COMPOSE_PROFILES=ai make up` | adds Ollama |
| Observability | `COMPOSE_PROFILES=observability make up` | Prometheus, Grafana, Jaeger |

## URLs (all bound to 127.0.0.1)

| What | URL |
|---|---|
| Web app (use this) | http://localhost:5173 |
| Gateway | http://localhost:8000 |
| Keycloak | http://localhost:8080 (admin password in `.env`) |
| RabbitMQ | http://localhost:15672 |
| MinIO | http://localhost:9001 |

## Personas

Log in through the persona switcher in the web app. Password for all: `Demo@2026!` (demo only).
Usernames and roles are in `infra/keycloak/realm-epfo-demo.json` and `init.md` §6.2.1.

## Isolation

- Networks and ports: `init.md` §2.4. Each service reaches only its own `data-<service>` network.
- Databases: one per service, created by `infra/database/init/01-create-databases.sh`; `infra/database/pg_hba.conf`
  lets each `<service>_app` role connect only to its own database and only from its own network subnet.
- The browser uses one origin (http://localhost:5173); the web server proxies `/auth` and `/api` to the gateway,
  so the gateway's `SameSite=Strict` session cookie works and no token ever reaches the browser.
