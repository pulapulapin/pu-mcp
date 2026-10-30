# Private runtime parity and publication boundary

Date: 2026-10-30. Reference runtime: local private 0.4.11 checkout. Public base:
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

| Capability | Private runtime 0.4.11 | Public feature branch | Decision |
| --- | --- | --- | --- |
| Core datasets, records, relations, preview/save | Available | Available | Shared base |
| Prompt fixed-version resolution and project differences | Available | Ported in this batch | Public generic core |
| Explicit writing-context recovery and readiness | Available | Ported in this batch | Public longform |
| Source selection, manuscript ranges and Markdown outline/fact anchors | Available | Ported in this batch | Public longform |
| Draft/Markdown quote verification | Available | Ported in this batch | Public longform/fs |
| Neutral corpus indexing and exact reads | Available | Ported in this batch | Public optional corpus extension |
| Candidate story graph and dependency impact paths | Implemented and host-discovered | Implemented on public feature branch | Same generic protocol; real project data remains private |
| Read-only story Schema bootstrap preview | Implemented; host refresh pending | Implemented on public feature branch | Exact pack and preview fingerprint; save remains separately authorized |
| Chapter-specific story graph context | Implemented and host-discovered | Implemented on public feature branch | Bounded candidate-graph context; external sources remain separate |
| Rule-based time/location/knowledge continuity | Implemented and host-discovered | Implemented on public feature branch | Conservative explicit-fact checks; unknowns stay insufficient evidence |
| Game repository/handoff tools | Private domain extension | Excluded | Keep private unless separately generalized |
| Voice experiments | Private domain extension | Excluded | Keep private |
| D&D classification/research-card compatibility | Private/legacy domain behavior | Excluded from new generic migration | Use external domain pack if ever published |
| Legacy Chat bridge and tunnel management | Deployment/compatibility | Excluded from capability parity | Local operations, not public product behavior |
| Embedded reader probe and host screenshots | Experimental/private acceptance | Excluded | Reassess as a separate UI feature |

The public package version remains 0.3.3 during feature development. Private
runtime version 0.4.11 must not be copied as a release number. Versioning is set
only when public scope, migration notes, packaging and host acceptance are ready.

## Verification for this synchronization batch

The public repository passes 266 tests. The verified scope includes prompt,
writing context, quote anchoring, source mapping, corpus, story planning,
chapter-specific graph context and conservative continuity review, plus real
stdio protocol tests using temporary projects. Tests do not read any private
project. Staged-content checks must reject real project names, user absolute
paths, private remote references, credentials, databases and acceptance
screenshots.

Passing tests prove bounded protocol behavior. Private host discovery separately
confirmed the five interfaces, but does not prove private project context is
complete, a candidate is Canon, or the resulting fiction is good. The public
branch was not installed into the private host.

## Next synchronization batch

Integrate the version-pinned candidate graph with Prompt, current task and
explicit external manuscript/Canon sources. The aggregate response must preserve
per-source authority and version, distinguish loaded/deferred/missing coverage,
and never promote candidates to Canon. A private runtime back-port, real project
import and host refresh remain separate preview, authorization and acceptance
steps.
