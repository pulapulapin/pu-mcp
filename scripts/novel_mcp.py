"""NOVEL 工作流的 MCP 业务层。

这里不依赖 MCP SDK，方便单元测试；longform_tools.py 负责把这些能力暴露给 MCP 宿主。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import novel_harness
import novel_session
from novel_config import load_settings

ROOT = Path(__file__).resolve().parent.parent
PROJECTS_ROOT = ROOT / "novels" / "projects"
DECISION_FIELDS = {
    "title",
    "core_conflict",
    "theme",
    "target_reader",
    "narrative_pov",
    "ending_direction",
}


def resolve_project(project: str) -> Path:
    if not project or Path(project).name != project or project in {".", ".."}:
        raise ValueError("项目ID无效")
    settings = load_settings()
    if project in settings.get('projects', {}):
        path = settings['projects'][project]
    else:
        root = settings['projects_dir']
        path = root / project
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('项目位于许可目录之外')
    if not path.is_dir() or not (path / "story-contract.json").is_file():
        raise ValueError(f"未找到小说项目：{project}")
    return path


def get_state(project: str) -> dict:
    path = resolve_project(project)
    validation = novel_harness.validate_project(path)
    data = novel_session.load_project(path)
    contract = data["contract"]
    return {
        "project": project,
        "path": str(path),
        "validation": validation,
        "contract": contract,
        "character_count": len(data["characters"].get("characters", [])),
        "timeline_count": len(data["timeline"].get("events", [])),
        "chapter_count": len(data["chapters"].get("chapters", [])),
        "next_task": novel_session.next_task(data),
    }


def get_context(project: str) -> dict:
    path = resolve_project(project)
    data = novel_session.load_project(path)
    return {
        "project": project,
        "path": str(path),
        "context": novel_session.confirmed_context(data),
        "next_task": novel_session.next_task(data),
    }


def start_session(project: str) -> dict:
    path = resolve_project(project)
    data = novel_session.load_project(path)
    task = novel_session.next_task(data)
    return {
        "project": project,
        "stage": task["label"],
        "task": task["instruction"],
        "context": novel_session.confirmed_context(data),
        "rules": [
            "只使用已确认内容作为Canon",
            "先提出方案和具体场景，不自动选定",
            "Owner未明确确认前不写回项目文件",
            "发现冲突时停止并说明冲突位置",
        ],
    }


def validate(project: str) -> dict:
    state = get_state(project)
    return {
        "project": project,
        "valid": state["validation"]["valid"],
        "status": state["validation"]["status"],
        "errors": state["validation"]["errors"],
        "next_task": state["next_task"],
    }


def save_confirmed_decision(
    project: str,
    field: str,
    value: str,
    owner_confirmed: bool = False,
    rationale: str = "",
) -> dict:
    """只保存 Owner 明确确认后的故事契约字段。"""
    if not owner_confirmed:
        raise ValueError("需要owner_confirmed=true；讨论候选方案不会自动写入Canon")
    if field not in DECISION_FIELDS:
        raise ValueError(f"不可直接写入的字段：{field}")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("value必须是非空文本")

    path = resolve_project(project)
    contract_path = path / "story-contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    previous = contract.get(field, "")
    contract[field] = value.strip()
    contract["status"] = "in_progress"
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    log_path = path / "decision-log.json"
    if log_path.is_file():
        log = json.loads(log_path.read_text(encoding="utf-8"))
    else:
        log = {"version": "1.0", "decisions": []}
    log["decisions"].append({
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "field": field,
        "previous": previous,
        "value": value.strip(),
        "rationale": rationale,
        "owner_confirmed": True,
    })
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "project": project, "field": field, "value": value.strip(), "next": get_state(project)["next_task"]}
