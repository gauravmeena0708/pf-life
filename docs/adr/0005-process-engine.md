# ADR-0005: Declarative process engine for office processes

- **Status:** Accepted (Gate 0, 2026-09-27)
- **Deciders:** project owner, Claude (architecture lead)

**Context.** About 230 catalogue operations are planned. Most office-side ones share one shape: submit → queue → maker-checker chain → state change → event (Joint Declaration, freeze, knock-off, TRRN adjustment, IDS/worksheet/PPO, recovery steps, audit paras, vigilance, legal cases, exemption decisions). Hand-coding each is not feasible in a POC.

**Decision.** `workflow-service` hosts a process engine that executes YAML process definitions: states, transitions, allowed roles, approval chain (from `docs/stakeholder-activities.yaml`), form schema, emitted events. The owning service registers its definitions and receives a completion event; the public contract stays with the owning service. The web app renders any process with one generic queue / case / decision screen. Journeys A–E stay hand-built.

**Alternatives.** Hand-code each (too slow); a BPMN engine such as Camunda/Flowable (heavy, Java, steep learning for agents).

**Consequences.** Many P rows can become W with little code, as each definition is added; those screens look generic rather than bespoke; the engine must enforce maker ≠ checker and amount bands itself, and is covered by the must-deny tests.
