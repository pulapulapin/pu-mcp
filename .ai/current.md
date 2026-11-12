# Public development status

Base: origin/main 828d618 (public package 0.3.3). Branch: feat/story-planning,
prepared as public 0.4.0 Alpha release candidate.
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

2026-11-12 product-value documentation batch: the public README now leads with
the user problem, concrete benefits, a typical long-project workflow and honest
host readiness. `docs/PRODUCT-VALUE.md` defines research, long-form writing,
product-decision and cross-agent scenarios, distinguishes PuKnowledge from chat
memory/files/RAG, and records pre-sales validation metrics. It contains no
private project data and does not claim unverified host compatibility as passed.

2026-11-12 onboarding batch completed: the public CLI now has explicit
`--init-workspace` configuration creation and a read-only `--doctor` report.
Initialization requires an existing directory and explicit project id/label,
refuses overwrite, writes a 0600 config, and does not create a database or edit
project content. Doctor checks config, projects, directory access and existing
SQLite integrity, returning READY/BLOCKED without initializing storage. The
initializer explicitly creates a generic `task` workspace and does not infer a
longform project. Public full suite: 279 passed.

2026-11-12 synthetic host compatibility batch completed: `puknowledge-compat`
starts this checkout's own stdio entry against temporary synthetic projects and
profiles basic stdio, tools-only clients, bounded responses and stale tool caches.
It checks preview/save/restart recovery, bounded fs reads and project isolation;
reports are fixed to `simulated=true` and `real_host_verified=false`. The work
also corrected the public `fs_read_file` implementation to match its existing
optional `review_items` tool signature. No private project or real-host claim is
part of this batch.

2026-11-12 manual real-host acceptance completed against separate ignored
synthetic databases: Cursor, TRAE and Claude Code CLI 2.1.311 all passed host tool
discovery, preview/save, fresh-session recovery and cross-project rejection. Claude
Code used a third-party model, so the result does not claim Anthropic model behavior.
Kimi Code was not run because the available account quota was exhausted. No real
project content or production database was used; longform behavior and clean-machine
installation remain separate gates.

2026-11-12 clean-install batch completed: a fresh Python 3.14 virtual environment
first exposed unconditional imports of unpublished `novel_game` and `domain_dnd`
modules. Public configuration now rejects nonempty `game_repositories`, generic
indexing uses the packaged default classifier, and a static import-closure test guards
the package module list. Rebuilt non-editable installation passed console init,
read-only doctor, all four synthetic compatibility profiles and dependency checks.
The public full suite now passes 287 tests. Other operating systems and independent
external-user installation remain unverified.

2026-11-12 synthetic longform batch completed: `puknowledge-compat` now includes a
fifth `longform-basic` profile. It creates two temporary fiction projects, discovers
the installed longform tools, previews and saves a versioned writing handoff and an
independent draft, proves both remain non-Canon/unapproved/unpublished, restarts the
MCP process for exact recovery, rejects cross-project reads and verifies that the
fixture JSON files were unchanged. The rebuilt non-editable Python 3.14 installation
passed this profile offline. Real manuscript quality and independent-user setup remain
separate gates.

2026-11-12 external-user gate prepared but not claimed as passed: the compatibility
CLI can now create a persistent, overwrite-safe four-project synthetic fixture and
print exact stdio launch parameters without creating a database or reading existing
user configuration. `docs/EXTERNAL-USER-ACCEPTANCE.md` reduces the independent test
to install/probe, one preview-authorized save, and a fresh-Chat recovery/isolation
check with a fixed report template. An actual uninvolved tester is still required.

2026-11-12 release-candidate preparation: public Python package, MCP server and
plugin manifest versions are aligned at 0.4.0 and guarded by a consistency test.
This is independent of the private runtime's 0.4.11 numbering. Merge to main,
tagging, GitHub Release and package publication remain unperformed approval gates.
The local wheel/sdist candidate built offline; the wheel installed into a fresh
Python 3.14 environment and passed doctor, dependency checks and all five synthetic
compatibility profiles. The 292-test suite passes without the prior SQLite
ResourceWarning after closing the test-only direct connection explicitly. Local
Python 3.11 was unavailable, so that interpreter remains a CI gate.

Verification: 292 public-repository tests passed, including synthetic host profiles,
Schema bootstrap, graph context and
continuity tests plus real stdio calls. Existing subprocess tests use the active
Python interpreter rather than assuming a checkout-local virtualenv. No package
release, production project import or real-project host test was performed.

2026-11-12 marketplace-readiness batch in progress: the repository now defines a
public Skill/MCP/project responsibility contract, privacy and preview-write rules,
commercial status vocabulary and publication gates. An unpublished Agensi Project
Continuity Starter candidate uses generic tools and data only. An offline validator
checks candidate metadata, required contracts, private absolute paths, selected
reserved private markers, terms from an uncommitted local denylist, embedded
credentials and external checkout references.
PuKnowledge remains `FREE_OPEN_SOURCE`; the candidate is `LISTING_CANDIDATE` and no
payment, subscription, quota or entitlement system has been added.

2026-11-12 distribution decision: after Agensi dependency/privacy/compatibility and
seller-payout feasibility are established, PuKnowledge should also receive a dedicated
`pustudio.cc` product entry, provisionally `/puknowledge/`. The existing `pustudio.cc`
thread has been handed a read-only planning brief. Agensi submission, marketplace
approval, website implementation, public deployment, merge and release remain separate
Owner gates; none is implied by this decision.

2026-11-12 Agensi submission-preparation batch: complete free Starter listing copy,
an unsent reply to the original outreach and deterministic text-only ZIP packaging
are now maintained separately. Packaging validates the Skill, rejects unexpected
candidate files, supports an external private-term denylist and reports the exact
archive hash with `submitted=false` and `published=false`. Account creation,
Creator Mode, upload, submission and email sending remain unperformed gates.

2026-11-12 Agensi visual-assets batch: a 512-square PuStudio-derived PuKnowledge
logo and three 1600x1000 synthetic walkthrough panels now cover exact recovery,
preview-before-save and project isolation. Editable SVG sources and PNG upload
files live outside the buyer ZIP and are guarded by dimension/privacy tests. They
remain Owner-review candidates; upload, submission, publication and email sending
are still unperformed. Recommended launch order is outreach reply, minimal
PuStudio product page and installable public release, then Agensi submission.

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
