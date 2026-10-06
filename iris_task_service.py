"""Independent task owner; survives dashboard and voice-worker restarts."""
import json
import secrets
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from iris_dev import ROOT
from iris_tasks import Tasks

PORT = 8766
TOKEN_FILE = ROOT / 'data' / 'task-service.token'

class TaskServer(ThreadingHTTPServer):
    allow_reuse_address = False
    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

def main():
    token = secrets.token_urlsafe(32)
    tasks = Tasks()
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.headers.get('X-Iris-Service') != token:
                self.send_error(403)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length < 24000: raise ValueError('Invalid request size')
                request = json.loads(self.rfile.read(length))
                result = {'result': tasks.dispatch(request['action'], request.get('data', {}))}
                code = 200
            except Exception as error:
                result, code = {'error': str(error)}, 400
            body = json.dumps(result).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *args): pass
    # Bind before publishing the token: concurrent starts cannot replace it.
    server = TaskServer(('127.0.0.1', PORT), Handler)
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = TOKEN_FILE.with_suffix('.tmp')
    temporary.write_text(token, encoding='utf-8')
    temporary.replace(TOKEN_FILE)
    server.serve_forever()

if __name__ == '__main__': main()
