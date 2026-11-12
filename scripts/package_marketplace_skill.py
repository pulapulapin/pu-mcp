#!/usr/bin/env python3
"""Build a deterministic, text-only Agensi Skill ZIP after local validation."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from validate_marketplace_skills import ROOT, validate


SKILL_ROOT = ROOT / "marketplace" / "agensi" / "project-continuity"
ARCHIVE_ROOT = "puknowledge-project-continuity-starter"
ALLOWED_FILES = (Path("SKILL.md"),)


def build(output: Path, private_terms: tuple[str, ...] = ()) -> dict[str, object]:
    skill = SKILL_ROOT / "SKILL.md"
    errors = validate(skill, private_terms)
    if errors:
        raise ValueError("marketplace validation failed: " + "; ".join(errors))
    unexpected = sorted(
        path.relative_to(SKILL_ROOT)
        for path in SKILL_ROOT.rglob("*")
        if path.is_file() and path.relative_to(SKILL_ROOT) not in ALLOWED_FILES
    )
    if unexpected:
        raise ValueError("unexpected candidate files: " + ", ".join(map(str, unexpected)))

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in ALLOWED_FILES:
            source = SKILL_ROOT / relative
            info = zipfile.ZipInfo(
                f"{ARCHIVE_ROOT}/{relative.as_posix()}",
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

    payload = output.read_bytes()
    return {
        "status": "READY",
        "output": str(output),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "files": [f"{ARCHIVE_ROOT}/{path.as_posix()}" for path in ALLOWED_FILES],
        "submitted": False,
        "published": False,
    }


def load_private_terms(path: Path | None) -> tuple[str, ...]:
    if not path:
        return ()
    return tuple(
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--private-terms-file",
        type=Path,
        help="Optional local denylist; keep it outside version control.",
    )
    args = parser.parse_args()
    report = build(args.output, load_private_terms(args.private_terms_file))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
