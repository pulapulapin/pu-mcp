# Candidate graph verification — 2026-10-30

Base: public main 828d618; branch feat/story-planning. No private history merge.

`python -m unittest discover -s tests -q`: 196 tests passed. The runtime already
had dependencies installed; no package/model/corpus downloads were required.
Existing loopback HTTP tests required permission to bind temporary local ports.

Nine new tests cover preview without business persistence, atomic mixed graph
save, idempotency/stale baseline, synthetic 48-chapter impact paths/history,
stale endpoint reporting, explicit rebind, withdrawal, cross-project refusal,
public dataset refusal, candidate-only states, invalid-prefix rollback,
containment cycles, fixed pagination and real stdio tool discovery/calls.
Core-only discovery remains unchanged; new tools load only with longform.

No real manuscript, source inventory, task snapshot, Canon, project configuration
or screenshot was imported. No production service was restarted. These tests do
not prove ordinary Chat behavior, semantic correctness, chapter restoration,
continuity rules, literary quality or packaging installation.
