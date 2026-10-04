"""
procnet.py — passive, generic Linux process/socket introspection.

Everything here reads kernel-exposed /proc files only. No app code is
touched, no packets are captured, no eBPF/OBI is used. This works for
any process regardless of language/runtime, containerized or not.
"""
import os
import socket as pysocket

TCP_STATE_ESTABLISHED = '01'
TCP_STATE_LISTEN = '0A'


def list_pids():
    """All PIDs currently visible under /proc."""
    pids = []
    for entry in os.listdir('/proc'):
        if entry.isdigit():
            pids.append(int(entry))
    return pids


def read_cmdline(pid):
    try:
        with open(f'/proc/{pid}/cmdline', 'rb') as f:
            data = f.read()
        parts = [p.decode('utf-8', 'replace') for p in data.split(b'\0') if p]
        return ' '.join(parts)
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return ''


def read_comm(pid):
    try:
        with open(f'/proc/{pid}/comm') as f:
            return f.read().strip()
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return ''


def read_env(pid):
    """Best-effort env read; requires matching uid or root. Returns {} on failure."""
    try:
        with open(f'/proc/{pid}/environ', 'rb') as f:
            data = f.read()
        env = {}
        for item in data.split(b'\0'):
            if b'=' not in item:
                continue
            k, v = item.split(b'=', 1)
            env[k.decode('utf-8', 'replace')] = v.decode('utf-8', 'replace')
        return env
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return {}


def interesting_env(env, limit=12):
    """Filter env vars down to ones plausibly describing service topology,
    dropping anything that looks like a secret."""
    SECRET_HINTS = ('PASSWORD', 'SECRET', 'TOKEN', 'KEY', 'PRIVATE')
    TOPOLOGY_HINTS = ('URL', 'HOST', 'PORT', 'SERVICE', 'DB', 'PG', 'ADDR', 'ENDPOINT')
    out = {}
    for k, v in env.items():
        ku = k.upper()
        if any(s in ku for s in SECRET_HINTS):
            continue
        if any(s in ku for s in TOPOLOGY_HINTS):
            out[k] = v
        if len(out) >= limit:
            break
    return out


def get_netns_id(pid):
    try:
        link = os.readlink(f'/proc/{pid}/ns/net')
        # format: 'net:[4026531840]'
        return link.split('[', 1)[1].rstrip(']')
    except (FileNotFoundError, ProcessLookupError, PermissionError, IndexError):
        return None


def representative_pid_per_netns(pids):
    """One representative PID per distinct network namespace. In a
    non-containerized host all processes share one namespace; each
    container gets its own, so this scales to both cases identically."""
    seen = {}
    for pid in pids:
        ns = get_netns_id(pid)
        if ns is not None and ns not in seen:
            seen[ns] = pid
    return list(seen.values())


def build_inode_owner_map(pids):
    """socket inode -> set of owning PIDs, via each process's open file descriptors."""
    owner = {}
    for pid in pids:
        try:
            fds = os.listdir(f'/proc/{pid}/fd')
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
        for fd in fds:
            try:
                link = os.readlink(f'/proc/{pid}/fd/{fd}')
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                continue
            if link.startswith('socket:['):
                inode = int(link[8:-1])
                owner.setdefault(inode, set()).add(pid)
    return owner


def _hex_to_ip(hex_str):
    if len(hex_str) == 8:  # IPv4, 32-bit little-endian
        b = bytes.fromhex(hex_str)
        return '.'.join(str(x) for x in b[::-1])
    if len(hex_str) == 32:  # IPv6, four little-endian 32-bit words
        b = bytes.fromhex(hex_str)
        chunks = [b[i:i + 4][::-1] for i in range(0, 16, 4)]
        raw = b''.join(chunks)
        return pysocket.inet_ntop(pysocket.AF_INET6, raw)
    return hex_str


def parse_tcp_file(path):
    """Parse /proc/<pid>/net/tcp or tcp6 into structured rows."""
    rows = []
    try:
        with open(path) as f:
            next(f, None)  # header line
            for line in f:
                parts = line.split()
                if len(parts) < 10:
                    continue
                local_ip_hex, local_port_hex = parts[1].split(':')
                remote_ip_hex, remote_port_hex = parts[2].split(':')
                rows.append({
                    'local_ip': _hex_to_ip(local_ip_hex),
                    'local_port': int(local_port_hex, 16),
                    'remote_ip': _hex_to_ip(remote_ip_hex),
                    'remote_port': int(remote_port_hex, 16),
                    'state': parts[3],
                    'inode': int(parts[9]),
                })
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return []
    return rows


def gather_all_tcp_rows(rep_pids):
    """Read the socket table once per distinct network namespace (via its
    representative PID), covering both tcp and tcp6."""
    rows = []
    for pid in rep_pids:
        for fname in ('tcp', 'tcp6'):
            for row in parse_tcp_file(f'/proc/{pid}/net/{fname}'):
                row['proto'] = fname
                rows.append(row)
    return rows
