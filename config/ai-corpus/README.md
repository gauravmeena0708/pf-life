# AI corpus (synthetic, illustrative)

Small, versioned documents the assistant may retrieve (init.md §8.2). Each file starts with a front-matter
block: `doc_id`, `title`, `version`, `classification`, `verified`. Paragraphs (blank-line separated) are
cited as `DOC-ID §n`.

Figures such as limits and service levels are written as placeholders — `{{rupees:claims.types.ADVANCE_ILLNESS.cap_paise}}`
or `{{grievances.reopen_window_days}}` — and filled from the rule set in force when an answer is given, so a policy
change published in Policy administration never leaves the assistant quoting old figures.

Classifications: `public` (anyone), `officer-restricted` (field-office staff and CAIU), `confidential`
(never retrieved by the assistant). The texts describe this proof of concept's own illustrative rules
(`config/demo-rules.yaml`), checked against the code — not the official EPF Scheme.

`PUB-099` is a deliberate test fixture: an unverified document with an embedded prompt-injection attempt,
used to show that access boundaries are enforced by application code (Journey E4).
