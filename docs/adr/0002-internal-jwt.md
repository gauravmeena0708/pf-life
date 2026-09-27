# ADR-0002: Gateway-signed internal JWT between gateway and services

- **Status:** Accepted (Gate 0, 2026-09-27)
- **Deciders:** project owner, Claude (architecture lead)

**Context.** Services must know who the caller is and what they may do. Forwarding the Keycloak token gives no domain grants; forwarding plain `X-Actor-*` headers lets anything on the network impersonate a user.

**Decision.** The gateway signs a short-lived JWT (Ed25519, 60 s, audience = target service) carrying subject, stakeholder ID, grants, office, jurisdiction, establishment, consumed step-up and correlation ID. Services verify it with the gateway's JWKS.

**Alternatives.** Token exchange in Keycloak (heavier, grants still outside Keycloak); mTLS with headers (complex locally).

**Consequences.** Services stay stateless about sessions; the key must rotate (JWKS supports two keys); a stolen internal token is useful for at most 60 s and one service.
