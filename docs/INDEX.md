# Project Documentation

This folder contains the six planning documents for **Global Economic Data Pipeline & Analytics Dashboard**.

1. [PRD.md](PRD.md) — product goals, users, requirements and acceptance criteria.
2. [TRD.md](TRD.md) — architecture, stack, API contract and engineering requirements.
3. [Backend_DB_Schema.md](Backend_DB_Schema.md) — table design, constraints, indexes and upsert rules.
4. [WebAppFlow.md](WebAppFlow.md) — page flows, API calls, and user-visible states.
5. [UIUX_design_spec.md](UIUX_design_spec.md) — design direction, layout, components and accessibility.
6. [implementation_plan.md](implementation_plan.md) — phased build plan and exit checks.

Supporting record:

- [DECISIONS.md](DECISIONS.md) — decision log (D-01 to D-36): each agreed decision from the Phase 0 review, with its rationale, impact, and any change from the v1.0 specifications. Detailed requirements stay in the six documents above.

Recommended order: PRD → TRD → DB Schema → Web App Flow → UI/UX Spec → Implementation Plan, with DECISIONS for the reasoning behind v1.1 changes. Keep these documents at `docs/` in the repository and ask Claude Code to consult them before implementing a phase.
