import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from iris_dev import ROOT
from iris_agents import codex_command, readable_events
from iris_tasks import Tasks

class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.jobs = MagicMock()
        self.jobs.agent_task.return_value = {'id':'agent-job'}
        self.tasks = Tasks(self.jobs, Path(self.temp.name)/'projects.json')
    def tearDown(self): self.temp.cleanup()

    def test_voice_drafts_without_executing(self):
        reply = self.tasks.voice('Ask Codex for Iris to explain ClassName in README.md')
        self.assertIn('Read-only', reply)
        self.jobs.agent_task.assert_not_called()
        review = self.tasks.pending_reviews()[0]
        self.assertEqual(review['prompt'], 'explain ClassName in README.md')
        self.tasks.voice('approve agent task')
        self.jobs.agent_task.assert_called_once_with(str(ROOT), review['prompt'], 'read-only')

    def test_replay_and_expiry_rejected(self):
        review = self.tasks.draft_agent('iris','Explain code','read-only')
        self.tasks.approve_review(review['id'])
        with self.assertRaises(ValueError): self.tasks.approve_review(review['id'])
        expired = self.tasks.draft_agent('iris','Explain code','read-only')
        with patch('iris_tasks.time.time', return_value=expired['expires']+1):
            with self.assertRaises(ValueError): self.tasks.approve_review(expired['id'])
        self.assertEqual(self.jobs.agent_task.call_count, 1)

    def test_file_edits_require_dashboard_review(self):
        review = self.tasks.draft_agent('iris','Fix the tests','workspace-write')
        reply = self.tasks.voice('approve agent task')
        self.assertIn('dashboard', reply)
        self.jobs.agent_task.assert_not_called()
        self.tasks.approve_review(review['id'])
        self.jobs.agent_task.assert_called_once()

    def test_cancel_removes_reviews(self):
        self.tasks.draft_agent('iris','Explain code','read-only')
        self.tasks.voice('cancel that')
        self.assertFalse(self.tasks.pending_reviews())

    def test_command_uses_prompt_file_not_interpolation(self):
        cmd = codex_command('E:/codex.exe', "E:/a'b/prompt.txt", 'E:/result.txt', 'read-only')
        self.assertIn("'E:/a''b/prompt.txt'", cmd)
        self.assertIn('--sandbox read-only', cmd)
        self.assertTrue(cmd.endswith(' -'))
        with self.assertRaises(ValueError): codex_command('x','p','r','danger-full-access')

    def test_readable_agent_events(self):
        result = readable_events('{"type":"item.completed","item":{"type":"agent_message","text":"Done"}}\n{"type":"turn.failed","error":{"message":"limit"}}\nstartup warning')
        self.assertIn('agent_message: Done',result)
        self.assertIn('limit',result)
        self.assertIn('startup warning',result)

if __name__ == '__main__': unittest.main()
