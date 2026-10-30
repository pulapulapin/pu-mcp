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
