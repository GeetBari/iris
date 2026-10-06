import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from iris_intents import validate, canonical
from iris_task_service import TaskServer
from http.server import BaseHTTPRequestHandler
from iris_dev import ROOT
from iris_tasks import Tasks

class TaskTests(unittest.TestCase):
    def test_service_port_is_exclusive(self):
        server = TaskServer(('127.0.0.1', 0), BaseHTTPRequestHandler)
        try:
            with self.assertRaises(OSError):
                TaskServer(server.server_address, BaseHTTPRequestHandler)
        finally:
            server.server_close()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.jobs = MagicMock()
        self.jobs.session.return_value = [{'id':'editor'}, {'id':'agent'}]
        self.jobs.start.return_value = {'id':'test'}
        self.jobs.items = {'test':{}}
        self.jobs.snapshot.return_value = []
        self.tasks = Tasks(self.jobs, Path(self.temp.name) / 'profiles.json')
    def tearDown(self): self.temp.cleanup()

    def test_session_and_editor_override(self):
        self.tasks.voice('Start coding on Iris with VS Code and Codex.')
        self.jobs.session.assert_called_once_with(str(ROOT), 'code', 'codex')
        self.assertEqual(self.tasks.last_ids, ['editor','agent'])

    def test_codex_speech_alias_in_tool_selection(self):
        for phrase in ['start coding on iris with vs code and codecs',
                       'start coding on iris using the vs code editor and code x agent please']:
            with self.subTest(phrase=phrase):
                self.jobs.session.reset_mock()
                self.tasks.voice(phrase)
                self.jobs.session.assert_called_once_with(str(ROOT), 'code', 'codex')

    def test_negation_and_unknown_tools_do_not_launch(self):
        self.tasks.voice("don't run tests")
        self.tasks.voice('start coding on iris using imaginary editor')
        self.jobs.start.assert_not_called()
        self.jobs.session.assert_not_called()

    def test_model_paraphrase_is_validated_and_executed(self):
        with patch('iris_tasks.interpret', return_value=validate({'action':'session','project':'iris','editor':'code','agent':'codex'}, self.tasks.profiles, 'iris')):
            self.tasks.voice('Fire up my coding setup')
        self.jobs.session.assert_called_once_with(str(ROOT), 'code', 'codex')

    def test_model_cannot_produce_shell_commands(self):
        with self.assertRaises(ValueError):
            validate({'action':'tests','project':'iris','command':'Remove-Item x'}, self.tasks.profiles, 'iris')
        with self.assertRaises(ValueError):
            validate({'action':'session','project':'missing'}, self.tasks.profiles, 'iris')
        self.assertEqual(canonical(validate({'action':'tests'}, self.tasks.profiles, 'iris')), 'run tests for iris')

    def test_regular_note_and_hypothetical_do_not_run_tests(self):
        self.assertIsNone(self.tasks.voice('take a note saying run tests for iris'))
        self.tasks.voice('how do I run tests for iris')
        self.jobs.start.assert_not_called()

    def test_context_and_conversation_persist(self):
        self.tasks.save_profile(dict(name='website',cwd=str(ROOT),editor='code',agent='',commands={}))
        self.tasks.voice('start coding on website')
        restored = Tasks(self.jobs, self.tasks.path)
        self.assertEqual(restored.active, 'website')
        self.assertEqual(restored.last_ids, ['editor','agent'])
        self.assertEqual(restored.events()[-1]['request'], 'start coding on website')

    def test_unknown_project_cannot_launch_default(self):
        answer = self.tasks.voice('Run tests for nonexistent')
        self.assertIn('do not know', answer)
        self.jobs.start.assert_not_called()
        self.tasks.voice('iris')
        self.jobs.start.assert_called_once()

    def test_profile_persistence_and_followup(self):
        self.tasks.save_profile(dict(name='website',cwd=str(ROOT),editor='code',agent='',commands={'tests':'Write-Output test'}))
        restored = Tasks(self.jobs, self.tasks.path)
        self.assertIn('website', restored.profiles)
        self.tasks.voice('start coding on website')
        self.tasks.voice('run its tests')
        self.jobs.start.assert_called_once_with('Write-Output test', str(ROOT))

    def test_port_validation_and_no_shell_injection(self):
        self.tasks.voice('What is using port 3000; Remove-Item something')
        command = self.jobs.start.call_args.args[0]
        self.assertIn('-LocalPort 3000', command)
        self.assertNotIn('Remove-Item', command)
        self.jobs.start.reset_mock()
        self.assertIn('65535', self.tasks.voice('check port 99999'))
        self.jobs.start.assert_not_called()

    def test_stop_only_recent_owned_job(self):
        self.tasks.last_ids = ['test']
        self.jobs.snapshot.return_value = [{'id':'test','can_stop':True,'label':'iris tests'},{'id':'other','can_stop':True}]
        self.tasks.voice('stop the task I just started')
        self.jobs.stop.assert_called_once_with('test')

    def test_missing_saved_command_and_unknown_intent(self):
        self.assertIn('No server command', self.tasks.voice('start the development server'))
        self.assertIsNone(self.tasks.voice('delete my files'))
        self.jobs.start.assert_not_called()

    def test_status_reports_actual_failure(self):
        self.tasks.last_ids = ['test']
        self.jobs.snapshot.return_value = [{'id':'test','label':'iris tests','status':'failed','exit_code':7}]
        self.assertIn('failed, exit code 7', self.tasks.voice('did they pass'))

if __name__ == '__main__': unittest.main()
