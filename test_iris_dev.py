import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
import iris_dev
import iris_dashboard

class DeveloperTests(unittest.TestCase):
    def test_interactive_terminal_environment(self):
        with patch.dict(iris_dev.os.environ, {'TERM': 'dumb'}):
            self.assertEqual(iris_dev.job_environment(True)['TERM'], 'xterm-256color')
            self.assertEqual(iris_dev.job_environment(False)['TERM'], 'dumb')
            self.assertEqual(iris_dev.os.environ['TERM'], 'dumb')

    def test_desktop_codex_uses_direct_mode(self):
        self.assertEqual(iris_dev.agent_arguments('codex', 'C:/Users/example/AppData/Local/OpenAI/Codex/bin/version/codex.exe'), ' --no-daemon')
        self.assertEqual(iris_dev.agent_arguments('codex', 'E:/tools/codex.cmd'), '')
        self.assertEqual(iris_dev.agent_arguments('claude', 'E:/tools/claude.exe'), '')

    def test_workspace_rejects_system_drive(self):
        with self.assertRaises(ValueError):
            iris_dev.workspace('C:/Windows')

    def test_jobs_output_exit_and_stop(self):
        with tempfile.TemporaryDirectory(dir=iris_dev.ROOT) as directory:
            with patch.object(iris_dev, 'DATA', Path(directory)):
                jobs = iris_dev.Jobs()
                job = jobs.start("Write-Output 'iris-smoke'; exit 7", str(iris_dev.ROOT))
                deadline = time.monotonic() + 15
                while job['id'] in jobs.processes and time.monotonic() < deadline:
                    time.sleep(.1)
                result = jobs.snapshot()[0]
                self.assertEqual(result['exit_code'], 7)
                self.assertEqual(result['status'], 'failed')
                self.assertIn('iris-smoke', result['output'])
                job = jobs.start('Start-Sleep -Seconds 30', str(iris_dev.ROOT))
                jobs.stop(job['id'])
                deadline = time.monotonic() + 5
                while job['id'] in jobs.processes and time.monotonic() < deadline:
                    time.sleep(.1)
                self.assertEqual(jobs.items[job['id']]['status'], 'stopped')

    def test_session_uses_literal_paths(self):
        with tempfile.TemporaryDirectory(dir=iris_dev.ROOT) as directory:
            with patch.object(iris_dev, 'DATA', Path(directory)):
                jobs = iris_dev.Jobs()
                with patch.object(jobs, 'start') as start, patch.object(iris_dev, 'discover', return_value=[{'id':'code','path':"E:/tools/a'b/code.cmd"}]):
                    jobs.session(str(iris_dev.ROOT), 'code', '')
                    self.assertIn("a''b", start.call_args.args[0])
                    self.assertFalse(start.call_args.args[2])

    def test_http_rejects_untrusted_execution(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), iris_dashboard.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        try:
            request = Request(base + '/dev', headers={'Host':'127.0.0.1:8765'})
            with urlopen(request) as response:
                self.assertIn(b'Developer Workspace', response.read())
            request = Request(base + '/api/dev/run', data=b'{}', headers={'Host':'127.0.0.1:8765','Origin':'https://untrusted.example'})
            with self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual(error.exception.code, 403)
            request = Request(base + '/api/dev/run', data=b'{}', headers={'Host':'127.0.0.1:8765','Origin':'http://127.0.0.1:8765'})
            with self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual(error.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()

if __name__ == '__main__':
    unittest.main()
