# Public development status

Base: origin/main 828d618 (public package 0.3.3). Branch: feat/story-planning.
This independent checkout contains only public history. No private code merge.

Scope: candidate story graph in longform using existing Knowledge versions,
private dataset permissions and transactions. Delivered batches now include
version-pinned graph read, mixed node/edge preview/save, explicit dependency
impact candidates, bounded chapter graph context and conservative rule-based
continuity review. Authority adoption and external-source aggregation remain
future work.

Boundary: no private project imports, runtime configs or manuscripts; synthetic
fixtures only. No production channel restart, automatic main merge or release.
See docs/design/story-planning.md for design and delivery boundaries.

Verification: 263 public-repository tests passed, including graph context and
continuity tests plus real stdio calls. Existing subprocess tests use the active
Python interpreter rather than assuming a checkout-local virtualenv. No package
release, real Chat host test or production project import was performed.

2026-10-30 parity batch: generic Prompt resolution, writing-context recovery,
source selection/ranges/maps/fact anchors, quote verification and neutral corpus
indexing were ported from the private 0.4.10 behavioral reference. Public full
suite passed 258 tests before the story-context batch and now passes 263 tests.
Private game/voice/D&D compatibility, deployment
tunnel, private examples and screenshots remain excluded. Current Chat binding
continues using the private runtime; no runtime switch or project write occurred.
See docs/design/private-runtime-parity.md.
