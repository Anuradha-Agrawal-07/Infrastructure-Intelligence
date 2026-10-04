#!/usr/bin/env python3

"""
Reusable automatic infrastructure discovery agent.

Modes:

1. Linux/passive mode:
       python discovery_agent.py

2. Windows + Docker Desktop mode:
       python discovery_agent.py --docker-desktop

Docker Desktop mode uses:
    Windows Docker CLI
        ->
    docker inspect
        ->
    docker exec
        ->
    container /proc/net/tcp

No service names are hardcoded.
"""

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone

import docker_meta
import procnet
import os
import docker_runtime

try:
    import docker_runtime
except ImportError:
    docker_runtime = None


def build_linux_topology(docker_socket=docker_meta.DEFAULT_SOCKET):
    """
    Original Linux /proc discovery implementation.
    Kept intact as a separate mode.
    """

    containers = docker_meta.get_enriched_containers(docker_socket)

    container_by_ip = {}
    container_by_pid = {}

    for c in containers:
        for net in c["networks"]:
            if net["ip"]:
                container_by_ip[net["ip"]] = c

        if c["pid"]:
            container_by_pid[c["pid"]] = c

    all_pids = procnet.list_pids()

    live_pids = [
        p for p in all_pids
        if procnet.read_cmdline(p)
    ]

    inode_owner = procnet.build_inode_owner_map(live_pids)
    rep_pids = procnet.representative_pid_per_netns(live_pids)
    tcp_rows = procnet.gather_all_tcp_rows(rep_pids)

    listen_owner_pid = {}

    for row in tcp_rows:
        if row["state"] != procnet.TCP_STATE_LISTEN:
            continue

        owners = inode_owner.get(row["inode"])

        if owners:
            listen_owner_pid[row["local_port"]] = next(iter(owners))

    nodes = {}

    def ensure_container_node(container):
        nid = f"container:{container['id']}"

        if nid not in nodes:
            nodes[nid] = {
                "id": nid,
                "type": "container",
                "name": container["name"],
                "image": container["image"],
                "labels": container["labels"],
                "state": container["state"],
                "networks": container["networks"],
                "env_hints": container["env_hints"],
                "observed_listening_ports": [],
                "identified_via": "docker_api",
            }

        return nid

    def ensure_process_node(pid):
        nid = f"process:{pid}"

        if nid not in nodes:
            nodes[nid] = {
                "id": nid,
                "type": "process",
                "name": procnet.read_comm(pid) or f"pid{pid}",
                "pid": pid,
                "cmdline": procnet.read_cmdline(pid)[:200],
                "observed_listening_ports": [],
                "identified_via": "procfs",
            }

        return nid

    def ensure_external_node(ip, port):
        nid = f"external:{ip}:{port}"

        if nid not in nodes:
            nodes[nid] = {
                "id": nid,
                "type": "external",
                "name": f"{ip}:{port}",
                "observed_listening_ports": [],
                "identified_via": "unresolved_endpoint",
            }

        return nid

    def identify_service_by_port(port):
        pid = listen_owner_pid.get(port)

        if pid is None:
            return None

        container = container_by_pid.get(pid)

        if container:
            return ensure_container_node(container)

        return ensure_process_node(pid)

    def identify_endpoint(ip, port, owner_pid=None):
        container = container_by_ip.get(ip)

        if container:
            return ensure_container_node(container)

        nid = identify_service_by_port(port)

        if nid:
            return nid

        if owner_pid is not None:
            container = container_by_pid.get(owner_pid)

            if container:
                return ensure_container_node(container)

            return ensure_process_node(owner_pid)

        return ensure_external_node(ip, port)

    for port, pid in listen_owner_pid.items():

        nid = identify_service_by_port(port)

        if nid and port not in nodes[nid]["observed_listening_ports"]:
            nodes[nid]["observed_listening_ports"].append(port)

    edges = {}

    for row in tcp_rows:

        if row["state"] != procnet.TCP_STATE_ESTABLISHED:
            continue

        if row["local_port"] in listen_owner_pid:
            continue

        if (
            row["remote_port"] not in listen_owner_pid
            and row["remote_ip"] not in container_by_ip
        ):
            continue

        owners = inode_owner.get(row["inode"])
        owner_pid = next(iter(owners)) if owners else None

        src_id = identify_endpoint(
            row["local_ip"],
            row["local_port"],
            owner_pid,
        )

        dst_id = identify_endpoint(
            row["remote_ip"],
            row["remote_port"],
        )

        if src_id == dst_id:
            continue

        key = (
            src_id,
            dst_id,
            row["remote_port"],
        )

        if key not in edges:
            edges[key] = {
                "count": 0,
                "proto": row["proto"],
            }

        edges[key]["count"] += 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "discovery_method": (
            "procfs_sockets"
            + ("+docker_api" if containers else "")
        ),
        "docker_enrichment_active": bool(containers),
        "nodes": list(nodes.values()),
        "edges": [
            {
                "source": src,
                "target": dst,
                "remote_port": port,
                "observed_connections": value["count"],
                "protocol": value["proto"],
                "evidence": "proc_net_tcp:ESTABLISHED",
            }
            for (src, dst, port), value in edges.items()
        ],
    }


def build_topology(
    docker_socket=docker_meta.DEFAULT_SOCKET,
    docker_desktop=False
):
    # Windows + Docker Desktop:
    # use the Docker CLI + container /proc/net/tcp collector.
    if sys.platform == "win32":
        if docker_runtime is None:
            raise RuntimeError(
                "docker_runtime.py could not be imported."
            )

        topology = docker_runtime.build_topology()

        topology["generated_at"] = (
            datetime.now(timezone.utc).isoformat()
        )

        return topology

    # Explicit Docker Desktop mode on other platforms.
    if docker_desktop:
        if docker_runtime is None:
            raise RuntimeError(
                "docker_runtime.py could not be imported."
            )

        topology = docker_runtime.build_topology()

        topology["generated_at"] = (
            datetime.now(timezone.utc).isoformat()
        )

        return topology

    # Existing Linux discovery path.
    return build_linux_topology(docker_socket)

def post_topology(topology, url):

    data = json.dumps(topology).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json"
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status





def save_snapshot(topology, output_dir="output"):
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%d_%H%M%S"
    )

    filename = os.path.join(
        output_dir,
        f"topology_{timestamp}.json"
    )

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(
            topology,
            f,
            indent=2
        )

    return filename



def main():

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--post",
        help="URL of receiver to POST topology JSON to",
    )

    parser.add_argument(
        "--out",
        help="Write topology JSON to this file",
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=0,
        help="Repeat every N seconds",
    )

    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON",
    )

    parser.add_argument(
        "--docker-socket",
        default=docker_meta.DEFAULT_SOCKET,
    )

    parser.add_argument(
        "--docker-desktop",
        action="store_true",
        help=(
            "Use Windows Docker Desktop runtime discovery "
            "through docker inspect + docker exec"
        ),
    )

    args = parser.parse_args()

    def run_once():

        topology = build_topology(
            args.docker_socket,
            args.docker_desktop,
        )
        
        snapshot_file = save_snapshot(topology)

        print(f"\n[discovery] Snapshot saved: {snapshot_file}")


        text = json.dumps(
            topology,
            indent=2 if args.pretty else None,
        )

        print(text)

        if args.out:

            with open(
                args.out,
                "w",
                encoding="utf-8",
            ) as f:
                f.write(
                    json.dumps(
                        topology,
                        indent=2,
                    )
                )

        if args.post:

            try:

                status = post_topology(
                    topology,
                    args.post,
                )

                print(
                    f"[discovery-agent] posted to "
                    f"{args.post} -> HTTP {status}",
                    file=sys.stderr,
                )

            except Exception as exc:

                print(
                    f"[discovery-agent] failed to post "
                    f"to {args.post}: {exc}",
                    file=sys.stderr,
                )

    if args.interval > 0:

        while True:

            try:
                run_once()

            except Exception as exc:

                print(
                    f"[discovery-agent] ERROR: {exc}",
                    file=sys.stderr,
                )

            time.sleep(args.interval)

    else:

        run_once()


if __name__ == "__main__":
    main()