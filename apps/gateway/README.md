# EPFO synthetic POC gateway

FastAPI BFF for the synthetic demonstration. It is not an official EPFO system. Browser tokens remain encrypted in Redis; the browser receives only the secure session cookie and readable double-submit CSRF cookie. The gateway enforces generated route status, stakeholder endpoint grants, revocation, step-up placeholders and service-scoped Ed25519 internal JWTs.

## Configuration

| Variable | Required | Purpose |
|---|---:|---|
| `REDIS_URL` | yes | Redis connection for sessions, OIDC state and revocation keys |
| `KEYCLOAK_ISSUER` | yes | Realm issuer, for example `http://keycloak:8080/realms/epfo-demo` |
| `KEYCLOAK_CLIENT_ID` | no | OIDC client (default `epfo-bff`) |
| `KEYCLOAK_CLIENT_SECRET` | yes | Confidential OIDC client secret |
| `GATEWAY_SESSION_FERNET_KEY` | yes | Fernet key for encrypted session values; generated ephemerally if unset |
| `GATEWAY_SIGNING_KEY_PEM` | recommended | PEM Ed25519 private key for internal JWTs; generated ephemerally if unset |
| `GATEWAY_PUBLIC_ORIGIN` | yes | Public gateway origin used for OIDC callback/logout URLs |
| `SESSION_IDLE_SECONDS` | no | Session idle lifetime (default 1800) |
| `SESSION_MAX_SECONDS` | no | Absolute session lifetime (default 28800) |

Generate a Fernet key with `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`. Set the gateway signing key to an Ed25519 PEM private key. Never commit either secret.

## Routes

Regenerate `app/routes.generated.json` from the catalogue and permission matrix:

```sh
python apps/gateway/tools/build_routes.py
```

The build calls `docs/tools/build_gate0.load_catalogue()` and reads `docs/permissions.yaml`. Literal paths are preferred over templates. Gateway-owned permission inspection is local; other gateway-owned routes and step-up verification are deferred, and machine callback HMAC verification is deferred to the later partner slice.

## Run

```sh
pip install '.[test]'
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Run commands from `apps/gateway/`. Container startup uses the same Uvicorn target. Endpoints `/health/live`, `/health/ready`, and `/internal/jwks` support runtime checks and service JWT verification.
