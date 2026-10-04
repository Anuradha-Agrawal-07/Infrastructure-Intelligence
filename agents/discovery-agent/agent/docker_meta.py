"""
docker_meta.py — optional, read-only enrichment via the Docker Engine API.

If /var/run/docker.sock isn't present or reachable, every function here
returns an empty result and the discovery agent falls back to pure
procfs-based identification. This module never creates, starts, stops,
or configures anything - GET requests only.
"""
import http.client
import json
import socket


DEFAULT_SOCKET = '/var/run/docker.sock'


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__('localhost')
        self._unix_path = path

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(self._unix_path)
        self.sock = sock


def _get(path, socket_path=DEFAULT_SOCKET, timeout=1.5):
    try:
        conn = _UnixHTTPConnection(socket_path)
        conn.timeout = timeout
        conn.request('GET', path)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        if resp.status != 200:
            return None
        return json.loads(data)
    except (OSError, json.JSONDecodeError, http.client.HTTPException):
        return None


def is_available(socket_path=DEFAULT_SOCKET):
    return _get('/version', socket_path) is not None


def _filter_env(env_list):
    SECRET_HINTS = ('PASSWORD', 'SECRET', 'TOKEN', 'KEY', 'PRIVATE')
    out = {}
    for item in env_list or []:
        if '=' not in item:
            continue
        k, v = item.split('=', 1)
        if any(s in k.upper() for s in SECRET_HINTS):
            continue
        out[k] = v
    return out


def get_enriched_containers(socket_path=DEFAULT_SOCKET):
    """List running containers with the metadata useful for topology
    identification: name, image, labels, networks (IPs), listening PID,
    published ports, and non-secret env vars."""
    base = _get('/containers/json', socket_path)
    if not base:
        return []

    result = []
    for c in base:
        detail = _get(f"/containers/{c['Id']}/json", socket_path)
        if not detail:
            continue
        networks = (detail.get('NetworkSettings') or {}).get('Networks') or {}
        net_list = [
            {'network': name, 'ip': info.get('IPAddress')}
            for name, info in networks.items() if info.get('IPAddress')
        ]
        result.append({
            'id': c['Id'][:12],
            'name': detail.get('Name', '').lstrip('/'),
            'image': (detail.get('Config') or {}).get('Image', ''),
            'labels': (detail.get('Config') or {}).get('Labels') or {},
            'pid': (detail.get('State') or {}).get('Pid'),
            'state': (detail.get('State') or {}).get('Status'),
            'networks': net_list,
            'published_ports': (detail.get('NetworkSettings') or {}).get('Ports') or {},
            'env_hints': _filter_env((detail.get('Config') or {}).get('Env')),
        })
    return result
