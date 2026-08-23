# Deterministic evaluations

`evaluations/cases.json` contains 20 representative cases spanning metadata, lineage, impact, SQL safety, governed
metric discovery, compatibility validation, lineage, undefined metrics, and chat-disabled behavior. Tests enforce a
unique, capability-balanced corpus and adapter/API tests assert the corresponding behavior offline.

Phase 3.1 replaces the compile-only yearly case with a confirmed 2018 revenue execution case. Integration tests cover
the fixed read-only database, bounded result, explicit-confirmation rejection, and mutation rejection.

Language quality evaluation is intentionally excluded from the deterministic gate because it would require a paid
provider. Provider behavior is covered with fakes/mocks; factual correctness remains grounded in tool contracts.
