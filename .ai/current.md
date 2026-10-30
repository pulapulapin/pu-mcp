# Public development status

Base: origin/main 828d618 (public package 0.3.3). Branch: feat/story-planning.
This independent checkout contains only public history. No private code merge.

Scope: candidate story graph in longform using existing Knowledge versions,
private dataset permissions and transactions. Delivered batches now include
read-only Schema Pack bootstrap preview, version-pinned graph read, mixed node/edge preview/save, explicit dependency
impact candidates, bounded chapter graph context and conservative rule-based
continuity review. Authority adoption and external-source aggregation remain
future work.

Boundary: no private project imports, runtime configs or manuscripts; synthetic
fixtures only. No production channel restart, automatic main merge or release.
See docs/design/story-planning.md for design and delivery boundaries.

Verification: 266 public-repository tests passed, including Schema bootstrap, graph context and
continuity tests plus real stdio calls. Existing subprocess tests use the active
Python interpreter rather than assuming a checkout-local virtualenv. No package
release, real Chat host test or production project import was performed.

2026-10-31 recovery parity batch: explicit manifests may be record-only but not
empty; persisted task references accept the documented `type`/`record_id` names
as well as legacy `kind`/`object_id`, reject conflicting aliases and foreign
project declarations, and remain version pinned. Projects with an explicit
recovery manifest no longer receive the legacy JSON story view in default
`writing_resume`/`writing_get_context` responses; legacy structure remains
available through separate structure tools. A checkpoint that conflicts with
the selected current session is returned as bounded historical metadata rather
than injecting its old summary, next step and evidence into default recovery;
the stored history remains unchanged. Public synthetic suite: 275 passed.

2026-10-30 parity batch: generic Prompt resolution, writing-context recovery,
source selection/ranges/maps/fact anchors, quote verification and neutral corpus
indexing were ported from the private 0.4.10 behavioral reference. Public full
suite passed 258 tests before the story-context batch and now passes 266 tests.
Private game/voice/D&D compatibility, deployment
tunnel, private examples and screenshots remain excluded. Current Chat binding
continues using the separately deployed private 0.4.11 runtime; its host tool
discovery passed independently. No private project write occurred during public
synchronization.
See docs/design/private-runtime-parity.md.
