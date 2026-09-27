# Request activity in the synthetic POC

`GET /api/v1/security/request-activity` is available only to the `ho.security`
demo role. The web view is `/security/activity`. It shows recent gateway API
requests, five-minute rates, challenge decisions, and the latest 100 request
records. The underlying Redis sorted set keeps at most 2,000 records and removes
records older than 24 hours. Restarting Redis discards the history.

Each record contains the time, HTTP method, **route template** (not a raw URL),
status, duration, correlation ID, authenticated subject and stakeholder when
known, the gateway socket peer IP, query/body **field names**, body byte count
when the gateway reads it, and rate/challenge decisions. Public establishment
and TRRN lookups also get a short keyed fingerprint of the searched identifier;
the key is regenerated on gateway restart. The dashboard does not store search
terms, TRRNs, OTPs, passwords, tokens, cookies, request bodies or response bodies.

The peer IP may be a reverse proxy or the local Vite server. It must not be
presented as a verified end-user IP without a configured trusted proxy chain.
An internet client MAC address is not available to this HTTP gateway. Anonymous
requests have no known user identity.

This is a short-lived POC operations view, not the durable, tamper-evident audit
trail or edge DDoS protection required for public deployment. The arithmetic
demo challenge remains a mock proof and should not be described as resistant to
automated solving.
