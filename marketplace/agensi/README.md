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
