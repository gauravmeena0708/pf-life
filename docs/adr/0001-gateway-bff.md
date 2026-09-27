# ADR-0001: Single FastAPI gateway as BFF; tokens stay server-side

- **Status:** Accepted (Gate 0, 2026-09-27)
- **Deciders:** project owner, Claude (architecture lead)

**Context.** 21 interfaces, 24 personas and 366 operations need one consistent place for authentication, authorisation, revocation, step-up and planned-endpoint handling. Browser-held tokens (SPA + PKCE) cannot be revoked instantly and are exposed to XSS.

**Decision.** `apps/gateway` (FastAPI) is the only entry point and acts as a Backend-for-Frontend. It runs the OIDC code flow with Keycloak, keeps tokens in Redis, and gives the browser an `HttpOnly; Secure; SameSite=Strict` cookie. Its route table is generated from `docs/endpoint-catalogue.md`.

**Alternatives.** Traefik/Kong plus SPA tokens (two components, tokens in browser, revocation harder); per-service auth (duplicated logic, drift).

**Consequences.** One place to enforce §6 of `init.md`; gateway is a single point of failure in the POC (acceptable locally); gateway must stay thin — no business logic.
