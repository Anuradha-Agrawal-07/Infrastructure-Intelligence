#!/usr/bin/env python3
"""
receiver.py — the minimum code needed to receive and display a discovered
topology. Deliberately dumb: no anomaly detection, no correlation, no
websockets, no persistence layer beyond a JSON file. Just:

  POST /topology  - accept a topology JSON blob and store it
  GET  /topology  - return the latest stored topology as JSON
  GET  /          - a plain HTML table view of the latest topology
"""
import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STORE_PATH = os.path.join(os.path.dirname(__file__), 'topology_latest.json')
_latest = {'nodes': [], 'edges': [], 'generated_at': None, 'discovery_method': None}


def _load_from_disk():
    global _latest
    if os.path.exists(STORE_PATH):
        try:
            with open(STORE_PATH) as f:
                _latest = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass


def _save_to_disk():
    with open(STORE_PATH, 'w') as f:
        json.dump(_latest, f, indent=2)


def _node_row(n):
    ports = ', '.join(str(p) for p in n.get('observed_listening_ports', [])) or '—'
    extra = n.get('image') or n.get('cmdline', '') or ''
    return f"""<tr>
      <td><code>{n['id']}</code></td>
      <td>{n.get('name','?')}</td>
      <td>{n.get('type','?')}</td>
      <td>{ports}</td>
      <td>{n.get('identified_via','?')}</td>
      <td style="color:#888;font-size:0.85em;">{extra}</td>
    </tr>"""


def _edge_row(e):
    return f"""<tr>
      <td><code>{e['source']}</code></td>
      <td>→</td>
      <td><code>{e['target']}</code></td>
      <td>:{e['remote_port']}</td>
      <td>{e['observed_connections']}</td>
      <td>{e.get('evidence','')}</td>
    </tr>"""


def _render_html():
    nodes = _latest.get('nodes', [])
    edges = _latest.get('edges', [])
    generated = _latest.get('generated_at') or 'never'
    method = _latest.get('discovery_method') or 'n/a'
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Discovered Topology</title>
<style>
  body {{ font-family: -apple-system, sans-serif; background: #0f1115; color: #e9ecf1; padding: 32px; }}
  h1 {{ font-size: 1.3rem; }}
  .meta {{ color: #9aa3b2; font-size: 0.85rem; margin-bottom: 24px; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 32px; }}
  th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid #2a2f3a; font-size: 0.88rem; }}
  th {{ color: #9aa3b2; font-weight: 600; }}
  code {{ color: #5b8cff; }}
  .empty {{ color: #9aa3b2; padding: 16px 0; }}
</style></head>
<body>
  <h1>Discovered Infrastructure Topology</h1>
  <div class="meta">generated_at: {generated} &nbsp;|&nbsp; discovery_method: {method} &nbsp;|&nbsp;
    nodes: {len(nodes)} &nbsp;|&nbsp; edges: {len(edges)} &nbsp;|&nbsp;
    <a href="/topology" style="color:#5b8cff;">raw JSON</a></div>

  <h2>Nodes</h2>
  {'<table><tr><th>id</th><th>name</th><th>type</th><th>observed listening ports</th><th>identified via</th><th>image / cmdline</th></tr>' + ''.join(_node_row(n) for n in nodes) + '</table>' if nodes else '<div class="empty">No topology received yet. Run the discovery agent with --post pointing at this receiver.</div>'}

  <h2>Edges (observed dependencies)</h2>
  {'<table><tr><th>source</th><th></th><th>target</th><th>port</th><th>observed connections</th><th>evidence</th></tr>' + ''.join(_edge_row(e) for e in edges) + '</table>' if edges else '<div class="empty">No edges observed yet.</div>'}
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[receiver] {self.address_string()} {fmt % args}")

    def do_GET(self):
        if self.path == '/topology':
            body = json.dumps(_latest, indent=2).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == '/':
            body = _render_html().encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        global _latest
        if self.path != '/topology':
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error": "invalid JSON"}')
            return
        payload['received_at'] = datetime.now(timezone.utc).isoformat()
        _latest = payload
        _save_to_disk()
        body = json.dumps({'status': 'ok', 'nodes': len(payload.get('nodes', [])), 'edges': len(payload.get('edges', []))}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8090)
    args = parser.parse_args()
    _load_from_disk()
    server = ThreadingHTTPServer(('0.0.0.0', args.port), Handler)
    print(f'[receiver] listening on port {args.port}')
    server.serve_forever()


if __name__ == '__main__':
    main()
