import json
import tempfile
import unittest
from pathlib import Path

from scripts.novel_harness import validate_project


class NovelHarnessTests(unittest.TestCase):
    def test_template_is_blocked_until_story_contract_is_filled(self):
        result = validate_project(Path("novels/_template"))
        self.assertFalse(result["valid"])
        self.assertEqual(result["status"], "return_for_story_setup")
        self.assertIn("故事契约缺少：core_conflict", result["errors"])

    def test_complete_minimal_project_can_enter_outline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "story-contract.json").write_text(json.dumps({
                "mode": "novel",
                "title": "夜班之后",
                "genre": "都市成长",
                "logline": "一个夜班青年在城市停电后重新认识自己的生活。",
                "core_conflict": "留下还是离开",
                "theme": "人如何重新选择自己的时间",
                "narrative_pov": "第三人称限知",
                "ending_direction": "开放但完成一次选择",
                "invariants": ["主角不能突然获得超能力"],
            }, ensure_ascii=False), encoding="utf-8")
            for filename, payload in {
                "characters.json": {"characters": []},
                "world.json": {"rules": []},
                "timeline.json": {"events": []},
                "chapters.json": {"chapters": []},
            }.items():
                (root / filename).write_text(json.dumps(payload), encoding="utf-8")
            result = validate_project(root)
            self.assertTrue(result["valid"])
            self.assertEqual(result["status"], "ready_for_outline")


if __name__ == "__main__":
    unittest.main()
