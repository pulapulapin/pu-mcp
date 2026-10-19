"""为 NOVEL 项目生成下一次 Chat 协作会话。

工作流不直接替作者写入 Canon，而是根据项目状态生成一个有边界的创作任务。
用户在 Chat 中讨论并确认后，再由后续流程落盘。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TASKS = {
    "core_conflict": {
        "label": "核心冲突",
        "instruction": "请帮助我从已确认的创作方向中提炼能推动第一卷的核心冲突。先提出3个有明显差异的候选，每个说明主角想要什么、阻碍是什么、为什么现在发生、能产生什么具体场景。不要直接替我选定。",
    },
    "theme": {
        "label": "主题",
        "instruction": "请在不拔高、不写空泛人生道理的前提下，讨论这个故事可能真正关心的主题。先提出2到3个方向，并说明每个方向如何通过人物选择和具体事件体现。不要把候选主题写入Canon。",
    },
    "narrative_pov": {
        "label": "叙事视角",
        "instruction": "请比较第一人称、第三人称限知和多视角对这个故事的影响。重点讨论巨龙身体体验、人物群像、家园日常和长篇节奏，不要只给抽象优缺点。",
    },
    "title": {
        "label": "暂定书名",
        "instruction": "请根据已经确认的故事方向提出一组暂定书名，并说明每个名字承诺了什么阅读体验。书名只是候选，不要把它当成最终决定。",
    },
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_project(path: Path) -> dict:
    contract = read_json(path / "story-contract.json")
    characters = read_json(path / "characters.json")
    world = read_json(path / "world.json")
    timeline = read_json(path / "timeline.json")
    chapters = read_json(path / "chapters.json")
    return {"contract": contract, "characters": characters, "world": world, "timeline": timeline, "chapters": chapters}


def next_task(project: dict) -> dict:
    contract = project["contract"]
    if contract.get('mode') in ('game_world','shared_world_novel'):
        return {'field':'joint_world_research','label':'跨媒介联合创作准备',
                'status':'needs_owner_input',
                'instruction':'先只读核对已登记的设计决定、实现与测试报告，区分已定、计划、实现、测试转述和AI推论；列出仍缺少依据的世界设定。不要自动确认设定或修改规则数值。'}
    for field, task in TASKS.items():
        if not isinstance(contract.get(field), str) or not contract[field].strip():
            return {"field": field, **task, "status": "needs_owner_input"}
    if not project["chapters"].get("chapters"):
        return {
            "field": "first_chapter",
            "label": "第一章方向",
            "status": "needs_owner_input",
            "instruction": "请根据已经确认的故事契约，提出3种不同的开篇方案。每种都要包含开场场景、主角当下处境、第一处具体麻烦和结尾留下的问题。先比较，不直接写正文。",
        }
    return {
        "field": "next_scene",
        "label": "下一场戏",
        "status": "ready_for_scene",
        "instruction": "请读取当前章节和人物状态，提出下一场戏的目标、阻碍、转折和后果。先给场景卡，等待确认后再写正文。",
    }


def confirmed_context(project: dict) -> dict:
    contract = project["contract"]
    return {
        "mode": contract.get("mode", "novel"),
        "project_id": contract.get("id", ""),
        "genre": contract.get("genre", ""),
        "logline": contract.get("logline", ""),
        "invariants": contract.get("invariants", []),
        "confirmed_characters": [
            {
                "id": item.get("id", ""),
                "role": item.get("role", ""),
                "species": item.get("species", ""),
                "identity": item.get("identity", ""),
                "confirmed_traits": item.get("confirmed_traits", []),
                "goals": item.get("goals", []),
            }
            for item in project["characters"].get("characters", [])
        ],
        "confirmed_rules": [item for item in project["world"].get("rules", []) if item.get("status") == "confirmed"],
        "timeline": [item for item in project["timeline"].get("events", []) if item.get("status") == "confirmed_premise"],
        "chapter_count": len(project["chapters"].get("chapters", [])),
    }


def build_prompt(project: dict, project_path: Path) -> str:
    task = next_task(project)
    context = confirmed_context(project)
    return f"""# NOVEL 协作会话｜{context['project_id']}

你是长篇创作项目的联合创作顾问。你负责提出方案、比较风险、设计具体场景；最终创作决策属于 Owner。当前阶段是：{task['label']}。

## 已确认内容

```json
{json.dumps(context, ensure_ascii=False, indent=2)}
```

## 本轮任务

{task['instruction']}

## 工作边界

- 只使用上面的已确认内容作为 Canon。
- 交接包中的候选、待确认和已否定内容不能自动升级为 Canon。
- 先给方案、具体场景和代价，再等待 Owner 选择。
- 不要直接开始长篇正文。
- 如果发现现有设定不足以回答，明确指出缺口。

讨论结束后，请用以下格式总结：

```text
本轮结论：
Owner 已确认：
仍待确认：
需要写入的文件：
与现有设定的冲突：
下一步建议：
```

项目路径：`{project_path}`
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 NOVEL 的 Chat 协作会话")
    parser.add_argument("command", choices=["next", "context", "prompt"])
    parser.add_argument("--path", required=True, type=Path)
    args = parser.parse_args()
    project = load_project(args.path)
    if args.command == "next":
        result = next_task(project)
    elif args.command == "context":
        result = confirmed_context(project)
    else:
        print(build_prompt(project, args.path))
        return 0
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
