# Lightweight story planning

Status: incremental development on the public 0.3.3 base, not a migration of
private runtime versions. Optional longform behavior reuses Knowledge storage.

## Responsibility boundary

Public code owns graph operations, schemas, transactions and access checks.
Projects own prose, plans, decisions, source mappings and approval scope. Public
examples/tests are fictional synthetic fixtures. No actual project is initialized
or imported by this change. Do not import private Git history or screenshots.

## First batch

A project-private purpose=model dataset and story_node schema must first be
explicitly previewed/saved using existing tools. The schema pack is distributed
in config/schemas/story-planning.json; nothing is created on read.

story_plan_get reads a fixed dataset snapshot (0 resolves latest once). Pagination
returns the resolved dataset_revision, which clients must reuse. Nodes and edges
carry exact revisions/fingerprints. Withdrawn nodes/edges are excluded from the
active view but remain in history. Stale endpoints are reported, not rebound.

story_plan_preview/save accept bounded candidate-node and edge changes. Existing
Knowledge record/relationship validation, dataset baseline and operation-key
journal are reused. All changes share one transaction/commit revision; invalid
endpoints or hierarchy cycles reject the whole batch. Preview uses a rollback-only
transaction to validate prospective node references. It leaves no business data.
It does not change prose, source files, task direction or Canon.

Only candidate/withdrawn writes are supported. Confirmed/adopted/occurred states
are intentionally not inferred from a boolean or a successful structure check.
Source bindings use existing version-pinned Record.evidence. No new provenance
or Canon database is created. Relation rows carry their own exact references;
this first batch does not support evidence on relationships.

Impact preview follows reverse depends_on paths and contains parents to identify
related chapters. It returns evidence paths from registered relations; shared
characters/locations and unregistered semantic implications are not proven causal
links. Both old and proposed graph paths are considered, including deleted edges.
Impact paths are capped at 200 rows and depth 32, with explicit truncation; stale endpoint details are capped at 50 with total counts. Limits and stale endpoints are explicit; results never mean all effects found.

Bounds: 100 node and 200 edge edits, 256KiB request; active graph <=2000 nodes and
6000 edges; read pages <=50 items. Missing/oversized graphs fail rather than
silently truncate. Candidate summaries are not full manuscripts.

## Chapter context and conservative continuity checks

`story_chapter_context` returns a fixed graph revision containing the selected
chapter, descendants, explicit prerequisites and directly related characters,
locations, states, setups and threads. Every node and edge carries a version and
fingerprint; node evidence bindings are returned without claiming the external
source body was loaded. Budget omissions and stale endpoints produce PARTIAL.
READY is explicitly scoped to the registered graph. Reader mode withholds the
candidate graph and returns BLOCKED because plans are not manuscript evidence.

`story_consistency_review` checks stale endpoints, invalid time ranges, overlapping
closed integer ranges at different locations explicitly marked exclusive, and
states established after an event that requires them. Missing or incomparable
time/state assertions return `insufficient_evidence`. Findings remain candidate
graph evidence; dramatic quality and Canon are not verified.

The schema pack gained optional story order, time domain/range, location-exclusive
and state fields. Existing experimental datasets created with the earlier schema
must preview/save the new schema revision before using these tools; relations are
never silently rebound. No production project was initialized by this change.

Synthetic acceptance: 48 chapters, changed event in chapter 27, explicit dependent
chapters, exact path reporting, history, stale endpoint reporting, atomic rollback,
idempotency, cross-project isolation, no automatic Canon. Actual Chat host tests
and private-project import previews are separate gates after implementation.

The next integration gate combines graph context with fixed task, Prompt and
external source recovery. Actual Chat host calls and private-project import
previews remain separate. No automatic manuscript generation or Agents.
