import unittest
import tempfile
from tests.support import create_story
from pathlib import Path

from scripts.novel_session import confirmed_context, load_project, next_task


class NovelSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        cls.path=create_story(Path(cls.temp.name)/'sample-story')
        cls.project=load_project(cls.path)

    def test_next_task_is_core_conflict(self):
        task = next_task(self.project)
        self.assertEqual(task["field"], "core_conflict")
        self.assertEqual(task["status"], "needs_owner_input")

    def test_context_contains_only_confirmed_rules(self):
        context = confirmed_context(self.project)
        self.assertEqual(context["project_id"], "sample-story")
        self.assertTrue(context["invariants"])
        self.assertEqual([item["id"] for item in context["confirmed_rules"]],["sample-rule"])


if __name__ == "__main__":
    unittest.main()
