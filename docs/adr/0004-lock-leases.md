# ADR-0004: Redis lock leases with TTL and fencing tokens

- **Status:** Accepted (Gate 0, 2026-09-27)
- **Deciders:** project owner, Claude (architecture lead)

**Context.** EPFO's Samadhan Setu tracker shows orphaned locks ("concurrent claims already under processing", "Unable to lock process") and the annual-accounts batch blocking claims.

**Decision.** Locks are Redis leases (`SET key NX PX ttl`) with heartbeat renewal and a monotonically increasing fencing token checked by the database on every write under the lock. Keys are hierarchical (`LOCK:MEMBER:ANNUAL_ACCOUNTING:{member_id}`, `LOCK:MEMBER:CLAIM:{member_id}:{claim_id}`, `LOCK:ESTABLISHMENT:ECR:{establishment_id}:{wage_month}`). Stale locks can be released under supervision with a reason (`LockReleased.v1`).

**Alternatives.** Database row flags (never expire; the production bug); advisory DB locks only (not visible across services).

**Consequences.** A crashed holder cannot block a member for more than the TTL; a holder that lost its lease cannot corrupt data; lock state is visible to officers and in the member's account status.
