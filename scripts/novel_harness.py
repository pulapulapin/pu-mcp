"""小说模式的结构与设定检查器。

只读检查故事契约、人物、世界观、时间线和章节卡是否存在且结构有效。
不生成正文，不替作者决定情节。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED_FILES = ("story-contract.json", "characters.json", "world.json", "timeline.json", "chapters.json")
CONTRACT_FIELDS = ("title", "genre", "logline", "core_conflict", "theme", "narrative_pov", "ending_direction")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_project(path: Path) -> dict:
    errors: list[str] = []
    files = {}
    for name in REQUIRED_FILES:
        file_path = path / name
        if not file_path.is_file():
            errors.append(f"缺少文件：{name}")
            continue
        try:
            files[name] = read_json(file_path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{name}无法读取：{exc}")

    contract = files.get("story-contract.json", {})
    if contract.get("mode") not in ("novel", "game_world", "shared_world_novel"):
        errors.append("story-contract.json的mode必须是novel/game_world/shared_world_novel")
    for field in (() if contract.get("mode") == "game_world" else CONTRACT_FIELDS):
        if not isinstance(contract.get(field), str) or not contract[field].strip():
            errors.append(f"故事契约缺少：{field}")
    if contract.get("mode") != "game_world" and (not isinstance(contract.get("invariants"), list) or not contract.get("invariants")):
        errors.append("故事契约至少需要一条invariants")

    for filename, collection_key in (("characters.json", "characters"), ("timeline.json", "events"), ("chapters.json", "chapters")):
        if filename in files and not isinstance(files[filename].get(collection_key), list):
            errors.append(f"{filename}.{collection_key}必须是数组")
    world = files.get("world.json", {})
    if "world.json" in files and not isinstance(world.get("rules"), list):
        errors.append("world.json.rules必须是数组")

    return {
        "path": str(path),
        "mode": contract.get("mode", "novel"),
        "valid": not errors,
        "status": ("ready_for_research" if contract.get("mode")=="game_world" else "ready_for_outline") if not errors else "return_for_story_setup",
        "errors": errors,
        "checks": {"files": len(files), "required_files": len(REQUIRED_FILES)},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="ai-plog 小说模式：故事结构与设定检查")
    parser.add_argument("command", choices=["validate"])
    parser.add_argument("--path", required=True, type=Path)
    args = parser.parse_args()
    result = validate_project(args.path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
