# Public development status

Base: origin/main 828d618 (public package 0.3.3). Branch: feat/story-planning.
This independent checkout contains only public history. No private code merge.

Scope: candidate story graph in longform using existing Knowledge versions,
private dataset permissions and transactions. First batch: version-pinned graph
read, mixed node/edge preview/save and explicit dependency impact candidates.
Chapter context, authority adoption and semantic consistency remain future work.

Boundary: no private project imports, runtime configs or manuscripts; synthetic
fixtures only. No production channel restart, automatic main merge or release.
See docs/design/story-planning.md for design and delivery boundaries.

Verification: 196 public-repository tests passed, including nine new graph tests
and a real stdio preview/save/read. Existing subprocess tests now use the active
Python interpreter rather than assuming a checkout-local virtualenv. No package
release, real Chat host test or production project import was performed.

2026-10-30 parity batch: generic Prompt resolution, writing-context recovery,
source selection/ranges/maps/fact anchors, quote verification and neutral corpus
indexing were ported from the private 0.4.10 behavioral reference. Public full
suite now passes 258 tests. Private game/voice/D&D compatibility, deployment
tunnel, private examples and screenshots remain excluded. Current Chat binding
continues using the private runtime; no runtime switch or project write occurred.
See docs/design/private-runtime-parity.md.
