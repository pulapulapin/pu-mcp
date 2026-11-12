# Agensi listing draft — PuKnowledge Project Continuity Starter

Status: `LISTING_CANDIDATE`. This file is submission copy, not part of the Skill
ZIP and not evidence that the listing is live.

## Listing fields

**Name**

PuKnowledge Project Continuity Starter

**Pricing**

Free. Keep this Starter listing free rather than converting it to paid later.

**Primary category**

Productivity

**Additional categories**

- Product Management
- Research & Analysis

**Summary**

Recover an explicit project's versioned task and next step in a new AI agent
session without relying on chat memory or mixing projects.

**Compatibility note**

Requires an independently installed PuKnowledge MCP 0.4.0+ with the `core`
module and task snapshot tools. Agensi delivers this workflow Skill; it does not
install or host the local MCP server.

**Tags**

- project continuity
- project memory
- cross-agent handoff
- traceable context
- versioned workflow
- local-first

**Use cases**

- Continue a multi-week project after opening a new chat or changing agents.
- Confirm which task revision and next step were actually restored.
- Save a non-Canon handoff through preview, explicit authorization and exact
  post-save verification.
- Verify that a session from one project does not fall back to another project.

## Description

Long-running AI projects become unreliable when the current task, approved
direction and next step live only in one chat. PuKnowledge Project Continuity
Starter gives an MCP-capable agent a narrow, auditable recovery workflow.

The Skill first checks that PuKnowledge is available, then lists explicitly
registered projects and restores only the project and session the user selects.
It reports the task ID, direction revision, next step, loaded sources and missing
context as `READY`, `PARTIAL` or `BLOCKED`.

When the user requests a new handoff, the Skill previews the exact change before
asking for authorization. A save must reuse the preview baseline and fingerprint,
and the agent reads the snapshot back afterwards. It never silently overwrites a
newer revision or promotes a task snapshot to Canon.

PuKnowledge runs locally and remains an independently installed open-source MCP.
The Skill author does not receive the user's project content, database, paths or
identifiers through this workflow.

This Starter does not write manuscripts, judge creative quality, install the MCP,
synchronize devices or provide cloud storage.

## See it in action

**Request**

> I opened a new agent session. Continue `acceptance-alpha` from the handoff
> `host-acceptance`, and tell me exactly what was restored. Do not change files.

**Result from a synthetic acceptance project**

```text
status: READY
project_id: acceptance-alpha
task_id: HOST-ACCEPTANCE-001
direction_revision: 1
next_step: Open a new agent session and recover this task.
sources_loaded:
  - exact session backup: host-acceptance, revision 1
missing_or_unverified:
  - factual correctness of the synthetic task was not evaluated
writes_performed: none
```

The same session ID queried under the separate synthetic project
`acceptance-beta` returned an explicit “session does not exist; no fallback”
result and exposed none of the Alpha task fields. This demonstration proves the
recovery and project-isolation workflow for the synthetic fixture; it does not
claim independent-user installation or real-project acceptance.

## Permissions and data

- Tools: the declared PuKnowledge MCP task tools.
- Files: no direct file access is required by this Starter.
- Network: the Skill itself makes no network request. The host may connect to
  Agensi to load the Skill and to the user's configured PuKnowledge MCP.
- Data destination: project state remains in the user's configured PuKnowledge
  storage. No project content is sent to the Skill creator.
- Writes: none by default. Snapshot writes require preview and explicit user
  authorization immediately before saving.

## Compatibility evidence

The public 0.4.0 release candidate has completed synthetic-project real-host
tool discovery, preview/save, fresh-session recovery and cross-project rejection
on Cursor, TRAE and Claude Code CLI 2.1.311 using a third-party model. These are
`real-host-synthetic-project` results, not independent external-user validation
and not a claim about every model or host version.

Other MCP-capable hosts may work but must not be presented as verified until the
same behavior has been tested there.

## Limitations

- PuKnowledge MCP must be installed and configured separately.
- The current public package is an Alpha release candidate.
- The Starter handles task continuity, not full longform or story-planning work.
- `READY` proves the selected handoff was restored, not that its claims are true
  or approved.
- There is no cloud synchronization, team account or hosted database.
- Independent external-user installation evidence is still being collected.

## FAQ

### Does Agensi install PuKnowledge for me?

No. Agensi delivers the Skill instructions. Install and configure the open-source
PuKnowledge MCP separately using its public documentation.

### Can the creator see my project?

Not through this workflow. The Skill instructs your agent to call your configured
PuKnowledge MCP. It does not upload project content to the creator.

### Does this make a snapshot Canon or an approved decision?

No. Task snapshots are working handoffs. They remain non-Canon unless the user
uses a separate project process to approve content.

### Does it edit my files?

No. This Starter uses task snapshot tools. It does not edit project files,
manuscripts or Canon.

### Which agents are verified?

The current public candidate has synthetic-project real-host evidence for Cursor,
TRAE and Claude Code CLI. See the compatibility notes for the exact evidence
level and limitations.

## Submission assets still required

- Square logo, 512 x 512 recommended. Use the public PuKnowledge identity only.
- Up to three screenshots: recovery report, preview-before-save and project
  isolation. Generate them from synthetic fixtures only.
- Optional short video after the public package can be installed by an
  independent tester.

## Public links

- Repository: https://github.com/pulapulapin/pu-mcp
- Release-candidate PR: https://github.com/pulapulapin/pu-mcp/pull/1
- Documentation: https://github.com/pulapulapin/pu-mcp#readme
