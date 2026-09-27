# ADR-0006: Contracts generated from the catalogue; detail through overlays

- **Status:** Accepted (Gate 0, 2026-09-27)
- **Deciders:** project owner, Claude (architecture lead)

**Context.** Endpoint lists, permissions and OpenAPI files drift when edited separately.

**Decision.** `docs/endpoint-catalogue.md` and `docs/stakeholder-activities.yaml` are the hand-maintained sources. `docs/tools/build_gate0.py` generates `contracts/openapi/*.yaml`, `docs/permissions.*`, `docs/api-matrix.md` and event schemas; hand-written request/response schemas live in `contracts/openapi/overlays/` and are merged in. Status, phase and callers can only come from the catalogue.

**Alternatives.** Hand-written OpenAPI per service (drift); code-first OpenAPI only (no contract before code).

**Consequences.** One command regenerates everything; CI checks catalogue ↔ OpenAPI ↔ implementation. After Gate 0, owners add schemas through overlays, not by editing generated files.
