"""Loopback-only UI integration harness. ALL accounts/files are synthetic test data.

The built React app uses the real Api/EventBus/JobRunner/AppController over HTTP.
Only desktop transport, fixture file pickers and account_base are adapted. Never
point this server at a real Lanzou account. Run via test-business-flow.mjs.
"""
from __future__ import annotations

import argparse
import hashlib
import http.server
import json
from pathlib import Path
import signal
import sys
import tempfile
import threading
import urllib.parse
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]
from mock_lanzou_account import MockLanzouAccount
from online.service import OnlineService
from online.provider_lanzou import MANIFEST_NAME
from online.paths import cloud_manifest_path
from pulses.core import paths
from pulses_web.api import Api
from pulses_web.controller import AppController
from pulses_web.events import EventBus, JobRunner


# This is a transport adapter, not a state/API mock. PS receives only real events.
ADAPTER = """<script>
window.pywebview = {api: Object.fromEntries(['invoke','pick_folder','pick_files'].map(name =>
 [name, async (...args) => (await fetch('/__bridge/' + name, {
 method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(args)
 })).json()]))};
let eventCursor = 0;
async function pump() {
 try {
  if (window.PS?.push) {
   const events = await (await fetch('/__events?after=' + eventCursor)).json();
   for (const event of events) { window.PS.push(event); eventCursor = event.seq; }
  }
 } finally { setTimeout(pump, 40); }
}
pump();
</script>"""


class Harness:
    def __init__(self, base, dist, mock):
        self.base, self.dist = base, dist
        self.pack = base / '模拟整合包_非真实账号'
        (self.pack / 'tacz').mkdir(parents=True)
        self.zips = []
        for name in ('alpha', 'beta', 'gamma'):
            target = base / f'{name}.zip'
            with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(f'{name}.json', json.dumps({'synthetic': True, 'name': name}))
            self.zips.append(str(target))
        self.file_index = 0
        self.mock = mock
        self.events, self.calls = [], []
        self.event_lock = threading.Lock()
        self.bus = EventBus()
        self.bus.set_sink(self.capture)
        self.ctrl = AppController(base_dir=base / 'db', bus=self.bus)
        self.jobs = JobRunner(self.bus, logger=self.ctrl.add_log)
        self.api = Api(self.ctrl, self.bus, self.jobs)

    def capture(self, event):
        with self.event_lock:
            self.events.append(event)

    def remote(self):
        # Read-only observation of the remote HTTP mock storage; no controller mutations.
        files = self.mock.state.files
        manifests = [json.loads(f['data']) for f in files.values()
                     if f['name'] == MANIFEST_NAME]
        cache = cloud_manifest_path(self.ctrl.db_path, self.ctrl.selected or '')
        cached = json.loads(cache.read_text()) if cache.is_file() else None
        return {'synthetic': True, 'manifests': manifests,
                'cachedManifestVersion': (cached or {}).get('version'),
                'fixtures': {Path(p).name: hashlib.sha256(Path(p).read_bytes()).hexdigest()
                             for p in self.zips},
                'shareRequests': [request for share in self.mock._shares.values()
                                  for request in share.state.requests],
                'folders': self.mock.state.folders,
                'files': [{'name': f['name'], 'folder': f['folder'],
                           'sha256': hashlib.sha256(f['data']).hexdigest()}
                          for f in files.values()],
                'uploads': list(self.mock.state.uploads),
                'deleted': list(self.mock.state.deleted),
                'logs': list(self.ctrl.logs),
                'calls': list(self.calls),
                'events': [{key: e[key] for key in ('v', 'seq', 'type', 'jobId')}
                           | {'data': {'message': (e.get('data') or {}).get('message', '')}}
                           for e in self.events if e['type'] in
                           ('job.done', 'job.error', 'job.cancelled')]}


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(args[2].harness.dist), **kwargs)

    def log_message(self, *args):
        pass  # Do not log login bodies, cookies or credentials.

    def reply(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        h = self.server.harness
        route = urllib.parse.urlparse(self.path)
        if route.path == '/__events':
            after = int(urllib.parse.parse_qs(route.query).get('after', ['0'])[0])
            with h.event_lock:
                return self.reply([e for e in h.events if e['seq'] > after])
        if route.path == '/__test/remote':
            return self.reply(h.remote())
        if route.path in ('/', '/index.html'):
            body = (h.dist / 'index.html').read_text().replace('<head>', '<head>' + ADAPTER).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        super().do_GET()

    def do_POST(self):
        h = self.server.harness
        args = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'[]')
        if self.path == '/__bridge/invoke':
            method, params = args
            # Record operation names and safe parameters only, never login credentials.
            result = h.api.invoke(method, params)
            h.calls.append({'method': method,
                            'params': {} if method == 'account.login' else params,
                            'jobId': (result.get('data') or {}).get('jobId')})
            return self.reply(result)
        if self.path == '/__bridge/pick_folder':
            return self.reply({'ok': True, 'data': {'path': str(h.pack)}})
        if self.path == '/__bridge/pick_files':
            if h.file_index >= len(h.zips):
                return self.reply({'ok': False, 'error': {'message': 'Fixture picker exhausted'}})
            selected = h.zips[h.file_index]
            h.file_index += 1
            return self.reply({'ok': True, 'data': {'paths': [selected]}})
        if self.path == '/__test/break-manifest':
            # Fault is solely in the HTTP mock: account share refresh also retains corruption.
            shares = list(h.mock._shares.values())
            if not shares:
                return self.reply({'error': 'No published share'}, 409)
            for share in shares:
                share.corrupt(MANIFEST_NAME)
            return self.reply({'synthetic': True, 'fault': 'manifest HTTP bytes corrupted'})
        self.reply({'error': 'Unknown route'}, 404)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, required=True)
    options = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='pulses-ui-synthetic-') as tmp:
        base = Path(tmp)
        # Isolate application data and account store from developer/user directories.
        mock = MockLanzouAccount('123456', 'synthetic-ui-password')
        mock.start()
        with patch.multiple(paths, DEFAULT_DB_DIR=base / 'default-db',
                            BOOTSTRAP_FILE=base / 'bootstrap.json',
                            LEGACY_BOOTSTRAP_FILE=base / 'legacy.json'), \
             patch('pulses_web.controller.OnlineService',
                   side_effect=lambda *a, **kw: OnlineService(*a, account_base=mock.base, **kw)):
            harness = Harness(base, options.dist.resolve(), mock)
            server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            server.daemon_threads = True
            server.harness = harness
            def stop(*_):
                threading.Thread(target=server.shutdown, daemon=True).start()
            signal.signal(signal.SIGTERM, stop)
            signal.signal(signal.SIGINT, stop)
            print(json.dumps({'url': f'http://127.0.0.1:{server.server_port}', 'synthetic': True}), flush=True)
            try:
                server.serve_forever()
            finally:
                if harness.ctrl.watcher:
                    harness.ctrl.watcher.stop()
                server.server_close()
                harness.mock.stop()


if __name__ == '__main__':
    main()
