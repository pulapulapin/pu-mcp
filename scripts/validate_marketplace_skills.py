#!/usr/bin/env python3
"""Validate public marketplace Skill candidates without third-party packages."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_ROOT = ROOT / "marketplace" / "agensi"
REQUIRED_FIELDS = {
    "name",
    "description",
    "summary",
    "version",
    "tags",
    "keywords",
    "use_cases",
    "docs_url",
}
REQUIRED_HEADINGS = {
    "## Workflow",
    "## Output contract",
    "## Safety and privacy",
    "## Known limitations",
}
FORBIDDEN_PATTERNS = {
    "absolute macOS user path": re.compile(r"/Users/[^/\s]+/"),
    "absolute Windows user path": re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+\\"),
    "private project identifier": re.compile(
        r"\b(?:owner-private-project|real-client-project)\b",
        re.IGNORECASE,
    ),
    "external checkout": re.compile(
        r"\b(?:gumroad|whop|lemonsqueezy|payhip|ko-fi|patreon)\b|buy\.stripe\.com",
        re.IGNORECASE,
    ),
    "embedded credential": re.compile(
        r"\b(?:api[_-]?key|access[_-]?token|password)\s*[:=]\s*[\"']?[^\s\"']{8,}",
        re.IGNORECASE,
    ),
}


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        raise ValueError("missing opening frontmatter delimiter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("missing closing frontmatter delimiter")
    raw = text[4:end]
    body = text[end + 5 :]
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        if not line or line.startswith((" ", "\t", "-")):
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return fields, body


def validate(path: Path, private_terms: tuple[str, ...] = ()) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    try:
        fields, body = parse_frontmatter(text)
    except ValueError as exc:
        return [str(exc)]

    missing = sorted(REQUIRED_FIELDS - fields.keys())
    if missing:
        errors.append("missing frontmatter fields: " + ", ".join(missing))
    if not re.fullmatch(r"\d+\.\d+\.\d+", fields.get("version", "")):
        errors.append("version must use MAJOR.MINOR.PATCH")
    if not fields.get("description", "").endswith("."):
        errors.append("description must state a complete observable result")
    if not fields.get("docs_url", "").startswith("https://"):
        errors.append("docs_url must use HTTPS")
    if "Requires: PuKnowledge MCP" not in body:
        errors.append("body must declare Requires: PuKnowledge MCP")
    for heading in sorted(REQUIRED_HEADINGS):
        if heading not in body:
            errors.append(f"missing required section: {heading}")
    for label, pattern in FORBIDDEN_PATTERNS.items():
        if pattern.search(text):
            errors.append(f"contains {label}")
    folded = text.casefold()
    for term in private_terms:
        if term.casefold() in folded:
            errors.append("contains a term from the local private denylist")
            break
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--private-terms-file",
        type=Path,
        help="Optional local file with one private term per line; never commit this file.",
    )
    args = parser.parse_args()
    private_terms: tuple[str, ...] = ()
    if args.private_terms_file:
        private_terms = tuple(
            line.strip()
            for line in args.private_terms_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    skills = sorted(CANDIDATE_ROOT.glob("**/SKILL.md"))
    if not skills:
        print("BLOCKED: no Agensi SKILL.md candidates found", file=sys.stderr)
        return 1
    failures = 0
    for path in skills:
        errors = validate(path, private_terms)
        relative = path.relative_to(ROOT)
        if errors:
            failures += 1
            print(f"FAIL {relative}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"PASS {relative}")
    if failures:
        print(f"BLOCKED: {failures} candidate(s) failed")
        return 1
    print(f"READY: {len(skills)} marketplace candidate(s) passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
