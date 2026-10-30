# Private runtime parity and publication boundary

Date: 2026-10-30. Reference runtime: local private 0.4.10 checkout. Public base:
0.3.3 plus `feat/story-planning`. This is a behavioral comparison, not permission
to copy private Git history or project data.

## Policy

The currently connected Chat may continue using the private runtime while public
parity is developed. Requirements are first exercised against that runtime when
they depend on its mature behavior. Reusable code is then ported as a reviewed
change with synthetic fixtures. A feature is not considered synchronized until
the public branch passes its own tests and contains no project material.

Public MCP owns protocols, bounded algorithms, schemas, permissions, versioning,
generic documentation and synthetic tests. Private projects own manuscripts,
Canon, outlines, character files, project prompts/customizations, decisions,
source inventories, task snapshots, databases, local paths and host screenshots.
Local plugin binding and runtime configuration remain private machine state.

Do not merge or cherry-pick the private branch wholesale. Do not publish private
commit history, `.ai` histories, verification captures or real project examples.
The public package must work with explicit external project configuration and
must never contain a default private project.

## Capability comparison

| Capability | Private runtime 0.4.10 | Public feature branch | Decision |
| --- | --- | --- | --- |
| Core datasets, records, relations, preview/save | Available | Available | Shared base |
| Prompt fixed-version resolution and project differences | Available | Ported in this batch | Public generic core |
| Explicit writing-context recovery and readiness | Available | Ported in this batch | Public longform |
| Source selection, manuscript ranges and Markdown outline/fact anchors | Available | Ported in this batch | Public longform |
| Draft/Markdown quote verification | Available | Ported in this batch | Public longform/fs |
| Neutral corpus indexing and exact reads | Available | Ported in this batch | Public optional corpus extension |
| Candidate story graph and dependency impact paths | Not loaded in current Chat | Implemented on public feature branch | Back-port only after public review; no production activation yet |
| Chapter-specific story graph context | Not complete | Not complete | Next generic batch |
| Rule-based time/location/knowledge continuity | Not complete | Not complete | Next generic batch |
| Game repository/handoff tools | Private domain extension | Excluded | Keep private unless separately generalized |
| Voice experiments | Private domain extension | Excluded | Keep private |
| D&D classification/research-card compatibility | Private/legacy domain behavior | Excluded from new generic migration | Use external domain pack if ever published |
| Legacy Chat bridge and tunnel management | Deployment/compatibility | Excluded from capability parity | Local operations, not public product behavior |
| Embedded reader probe and host screenshots | Experimental/private acceptance | Excluded | Reassess as a separate UI feature |

The public package version remains 0.3.3 during feature development. Private
runtime version 0.4.10 must not be copied as a release number. Versioning is set
only when public scope, migration notes, packaging and host acceptance are ready.

## Verification for this synchronization batch

The public repository passes 258 tests. The batch includes prompt, writing
context, quote anchoring, source mapping, corpus and story-planning tests, plus
real stdio protocol tests using temporary projects. Tests do not read any private
project. Staged-content checks must reject real project names, user absolute paths,
private remote references, credentials, databases and acceptance screenshots.

Passing tests prove bounded protocol behavior. They do not prove current Chat has
refreshed tools, private project context is complete, a candidate is Canon, or the
resulting fiction is good. Current Chat remains on the private runtime until an
explicit migration and host acceptance task.

## Next synchronization batch

Build chapter context on the version-pinned candidate graph: selected chapter,
explicit predecessors, character states at that story point, open setups and
loaded/deferred/missing source coverage. Then add conservative continuity rules
for comparable time ranges, mutually exclusive locations and explicit knowledge
prerequisites. Missing assertions return `insufficient_evidence`. Use synthetic
fixtures first; a real project import remains a separate private preview and
authorization step.
