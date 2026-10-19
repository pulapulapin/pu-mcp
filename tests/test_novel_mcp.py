import json
import unittest
import tempfile,os
from unittest.mock import patch
from tests.support import create_story
from pathlib import Path

from scripts import novel_mcp


class NovelMcpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);create_story(root/'projects/sample-story')
        config=root/'config.json';config.write_text(json.dumps({'projects_dir':str(root/'projects'),'data_dir':str(root/'data')}))
        env=patch.dict(os.environ,{'NOVEL_WORKBENCH_CONFIG':str(config),'PUKNOWLEDGE_CONFIG':str(config)})
        env.start();self.addCleanup(env.stop)

    def test_start_session_reads_isolated_story_state(self):
        result = novel_mcp.start_session("sample-story")
        self.assertEqual(result["stage"], "核心冲突")
        self.assertEqual(result["context"]["project_id"], "sample-story")

    def test_save_requires_owner_confirmation(self):
        with self.assertRaises(ValueError):
            novel_mcp.save_confirmed_decision("sample-story", "core_conflict", "测试", owner_confirmed=False)

    def test_invalid_project_is_rejected(self):
        with self.assertRaises(ValueError):
            novel_mcp.get_state("../outside-project")


if __name__ == "__main__":
    unittest.main()
