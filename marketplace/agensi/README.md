# Agensi publication candidates

This directory contains reviewable marketplace candidates. Nothing here has
been submitted to, approved by, or published on Agensi.

- PuKnowledge remains an independently installed local MCP dependency.
- Candidates contain generic workflow instructions only.
- Never add user databases, manuscripts, project names, local paths, secrets,
  payment data, or private acceptance evidence.
- Validate candidates before packaging:

```bash
python3 scripts/validate_marketplace_skills.py
```

Before a public submission, maintainers can also supply a local, uncommitted
one-term-per-line denylist:

```bash
python3 scripts/validate_marketplace_skills.py \
  --private-terms-file /absolute/path/outside/the/repository/private-terms.txt
```

The product and publication contract is defined in
[`docs/MARKETPLACE-SKILL-STANDARD.md`](../../docs/MARKETPLACE-SKILL-STANDARD.md).

Build a deterministic submission candidate outside the repository:

```bash
python3 scripts/package_marketplace_skill.py \
  --output /tmp/puknowledge-project-continuity-starter-0.1.0.zip
```

The command validates the candidate, rejects unexpected files and reports its
SHA-256. It does not sign in, upload, submit or publish anything. Listing copy is
kept separately in `marketplace/agensi/submission/` and is intentionally excluded
from the buyer ZIP.
