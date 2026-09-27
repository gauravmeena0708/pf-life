# ADR-0007: Local Docker Compose runtime; full and lite modes

- **Status:** Accepted (Gate 0, 2026-09-27)
- **Deciders:** project owner, Claude (architecture lead)

**Context.** The POC runs on one laptop (WSL, 9 GB RAM, 8 CPUs) for both domain and technical audiences.

**Decision.** Docker Compose with profiles. Full mode runs every service in its own container (~3 GB); lite mode lowers workers and pools and disables optional profiles (~2 GB). All host ports bind to `127.0.0.1`. `make up | seed | test | demo | down | reset` are the only commands a user needs.

**Alternatives.** Kubernetes (kind/minikube: heavier, slower for agents); a single process running all services (breaks the service-boundary demonstration).

**Consequences.** Anyone with Docker can run it; sharing with others later needs a server, TLS and access control (not in slice 1).
