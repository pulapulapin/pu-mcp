# PuKnowledge 0.4.0 Alpha release candidate

Date: 2026-11-12

This candidate expands the public 0.3.3 base into a local-first workbench for
traceable long-running research, product and long-form writing projects. It does
not include private project data, private domain extensions or a hosted service.

## Highlights

- Fixed-version global Prompt templates with project-private customizations.
- Explicit writing-context recovery with `READY` / `PARTIAL` / `BLOCKED` states.
- Candidate story planning, chapter context, impact paths and conservative
  continuity findings without promoting candidates to Canon.
- Project-local SQLite shadow-copy, verification and explicit active routing.
- Safe workspace initialization, read-only doctor checks and synthetic host probes.
- Neutral corpus indexing, exact-version reads and bounded file quote anchors.

## Upgrade and compatibility notes

- Back up existing SQLite data before changing a production configuration.
- Existing project files remain the content authority; installation does not move,
  rewrite or import manuscripts, Canon or Markdown files.
- Project-local database routing remains explicit. Creating or verifying a shadow
  database does not switch active routing.
- Public 0.4.0 rejects nonempty `game_repositories`. Private game/domain adapters
  are not part of this package and must not be represented as public support.
- Public long-form APIs and the legacy local CLI require an explicit project; there
  is no default D&D project or project-specific narrative prompt.
- Dormant legacy edition classifiers remain packaged for old local data compatibility,
  but are not public default MCP modules. Their migration/removal remains future work.
- Candidate story graph saves remain non-Canon. Schema or consistency checks do not
  establish literary quality, factual truth or Owner approval.

## Verification evidence

- 292 public tests pass on the maintainer's macOS environment.
- A non-editable Python 3.14 installation passed doctor, dependency checks and all
  five synthetic compatibility profiles.
- Cursor, TRAE and Claude Code CLI 2.1.311 completed synthetic tool discovery,
  preview/save, fresh-session recovery and project-isolation checks before the
  release version was raised. Claude Code used a third-party model.
- The source tree and release materials contain synthetic fixtures only; private
  manuscripts, databases, absolute user paths and host screenshots are excluded.

## Not yet verified

- Independent external-user installation and continued-use value.
- Windows and Linux installation.
- Real-project literary quality or full manuscript/Canon recovery.
- Official Anthropic-model behavior, Kimi Code, VS Code Agent and every future host.
- Multi-user or unauthenticated public HTTP deployment.

## Remaining release gates

- [x] Align Python package, MCP handshake and plugin versions at 0.4.0.
- [x] Build and install-test the candidate artifact locally.
- [x] Run the public test suite and synthetic compatibility profiles after versioning.
- [ ] Review and merge the feature branch to `main`.
- [ ] Confirm CI on the merged commit.
- [ ] Create the `v0.4.0` tag and public GitHub Release.
- [ ] Publish a package only if a distribution channel is intentionally selected.
- [ ] Collect post-release independent-user acceptance using
  [EXTERNAL-USER-ACCEPTANCE.md](EXTERNAL-USER-ACCEPTANCE.md).
