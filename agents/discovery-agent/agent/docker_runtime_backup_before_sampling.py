"""
docker_runtime.py

Windows-native Docker Desktop runtime discovery.

Discovers:
- running containers
- container IPs
- listening ports
- container-to-container TCP connections

Uses:
- Docker CLI
- docker inspect
- docker exec
- /proc/net/tcp

No WSL.
No Ubuntu.
No Docker socket.
No hardcoded service names.
"""

import json
import socket
import struct
import subprocess


TCP_ESTABLISHED = "01"
TCP_TIME_WAIT = "06"
TCP_LISTEN = "0A"


def run_docker(args, timeout=10):
    result = subprocess.run(
        ["docker"] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"docker {' '.join(args)} failed:\n"
            f"{result.stderr.strip()}"
        )

    return result.stdout.strip()


# ---------------------------------------------------------
# Docker container discovery
# ---------------------------------------------------------

def get_containers():
    output = run_docker(["ps", "-q"])

    if not output:
        return []

    containers = []

    for container_id in output.splitlines():
        container_id = container_id.strip()

        if not container_id:
            continue

        raw = run_docker(["inspect", container_id])
        data = json.loads(raw)[0]

        networks = []

        network_settings = data.get(
            "NetworkSettings",
            {}
        )

        network_map = network_settings.get(
            "Networks",
            {}
        )

        for network_name, network_data in network_map.items():
            ip = network_data.get("IPAddress", "")

            networks.append({
                "name": network_name,
                "ip": ip,
            })

        # -------------------------------------------------
        # Docker-configured ports
        # -------------------------------------------------

        exposed_ports = []

        config_exposed = (
            data.get("Config", {})
            .get("ExposedPorts", {})
        )

        if config_exposed:
            for port_proto in config_exposed.keys():
                try:
                    port = int(
                        port_proto.split("/")[0]
                    )

                    exposed_ports.append(port)

                except ValueError:
                    pass

        container = {
            "id": data.get("Id", "")[:12],

            "full_id": data.get(
                "Id",
                ""
            ),

            "name": data.get(
                "Name",
                ""
            ).lstrip("/"),

            "image": data.get(
                "Config",
                {}
            ).get(
                "Image",
                ""
            ),

            "state": data.get(
                "State",
                {}
            ).get(
                "Status",
                ""
            ),

            "networks": networks,

            "exposed_ports": sorted(
                set(exposed_ports)
            ),
        }

        containers.append(container)

    return containers


# ---------------------------------------------------------
# /proc/net/tcp IP decoding
# ---------------------------------------------------------

def ip_from_proc_hex(hex_ip):
    value = int(
        hex_ip,
        16
    )

    # /proc/net/tcp stores IPv4 addresses
    # in little-endian form.
    packed = struct.pack(
        "<I",
        value
    )

    return socket.inet_ntoa(packed)


# ---------------------------------------------------------
# TCP parser
# ---------------------------------------------------------

def parse_proc_tcp(text):
    rows = []

    for line in text.splitlines():

        line = line.strip()

        if not line:
            continue

        if line.startswith("sl"):
            continue

        parts = line.split()

        if len(parts) < 4:
            continue

        local = parts[1]
        remote = parts[2]
        state = parts[3]

        try:
            local_ip_hex, local_port_hex = (
                local.split(":")
            )

            remote_ip_hex, remote_port_hex = (
                remote.split(":")
            )

            local_ip = ip_from_proc_hex(
                local_ip_hex
            )

            remote_ip = ip_from_proc_hex(
                remote_ip_hex
            )

            local_port = int(
                local_port_hex,
                16
            )

            remote_port = int(
                remote_port_hex,
                16
            )

        except (
            ValueError,
            OSError
        ):
            continue

        rows.append({
            "local_ip": local_ip,
            "local_port": local_port,

            "remote_ip": remote_ip,
            "remote_port": remote_port,

            "state": state,

            "proto": "tcp",
        })

    return rows


# ---------------------------------------------------------
# Read TCP table from inside container
# ---------------------------------------------------------

def read_container_tcp(container_name):

    commands = [
        [
            "exec",
            container_name,
            "cat",
            "/proc/net/tcp",
        ],

        [
            "exec",
            container_name,
            "/bin/sh",
            "-c",
            "cat /proc/net/tcp",
        ],
    ]

    last_error = None

    for command in commands:

        try:
            return run_docker(
                command,
                timeout=5
            )

        except Exception as exc:
            last_error = exc

    raise RuntimeError(
        f"Could not read /proc/net/tcp "
        f"from {container_name}: "
        f"{last_error}"
    )


# ---------------------------------------------------------
# Ignore obvious ephemeral/system listeners
# ---------------------------------------------------------

def is_useful_listening_port(
    port,
    container
):

    # Prefer Docker's declared application ports.
    exposed_ports = container.get(
        "exposed_ports",
        []
    )

    if exposed_ports:
        return port in exposed_ports

    # If Docker metadata doesn't expose ports,
    # keep the listener because it may still be useful.
    return True


# ---------------------------------------------------------
# Build topology
# ---------------------------------------------------------

def build_topology():

    containers = get_containers()

    # -----------------------------------------------------
    # Map container IP -> container
    # -----------------------------------------------------

    container_by_ip = {}

    for container in containers:

        for network in container["networks"]:

            ip = network.get("ip")

            if ip:
                container_by_ip[ip] = container

    # -----------------------------------------------------
    # Create container nodes
    # -----------------------------------------------------

    nodes = {}

    for container in containers:

        node_id = (
            f"container:{container['id']}"
        )

        nodes[node_id] = {
            "id": node_id,

            "type": "container",

            "name": container["name"],

            "image": container["image"],

            "state": container["state"],

            "networks": container["networks"],

            "docker_exposed_ports": (
                container["exposed_ports"]
            ),

            "observed_listening_ports": [],

            "identified_via": (
                "docker_cli+container_procfs"
            ),
        }

    # -----------------------------------------------------
    # Collect TCP observations
    # -----------------------------------------------------

    all_rows = []

    for container in containers:

        name = container["name"]

        node_id = (
            f"container:{container['id']}"
        )

        try:

            tcp_text = read_container_tcp(
                name
            )

            rows = parse_proc_tcp(
                tcp_text
            )

        except Exception as exc:

            print(
                f"[docker-runtime] warning: "
                f"{name}: {exc}"
            )

            continue

        # -------------------------------------------------
        # Record useful listening ports
        # -------------------------------------------------

        for row in rows:

            if row["state"] != TCP_LISTEN:
                continue

            port = row["local_port"]

            if not is_useful_listening_port(
                port,
                container
            ):
                continue

            if (
                port
                not in nodes[node_id][
                    "observed_listening_ports"
                ]
            ):

                nodes[node_id][
                    "observed_listening_ports"
                ].append(port)

        # -------------------------------------------------
        # Save TCP observations
        # -------------------------------------------------

        for row in rows:

            row["container"] = container

            all_rows.append(row)

    # -----------------------------------------------------
    # Determine listening ports per container
    # -----------------------------------------------------

    listening_ports_by_container = {}

    for row in all_rows:

        if row["state"] != TCP_LISTEN:
            continue

        container_id = (
            row["container"]["id"]
        )

        listening_ports_by_container.setdefault(
            container_id,
            set()
        ).add(
            row["local_port"]
        )

    # -----------------------------------------------------
    # Build service-to-service edges
    # -----------------------------------------------------

    edges = {}

    for row in all_rows:

        # Only active or recently active connections.
        if row["state"] not in (
            TCP_ESTABLISHED,
            TCP_TIME_WAIT,
        ):
            continue

        local_container = row["container"]

        local_id = (
            f"container:{local_container['id']}"
        )

        # -------------------------------------------------
        # Find container owning remote IP
        # -------------------------------------------------

        remote_container = container_by_ip.get(
            row["remote_ip"]
        )

        if remote_container is None:
            continue

        remote_id = (
            f"container:{remote_container['id']}"
        )

        # Ignore self-connections.
        if local_id == remote_id:
            continue

        # -------------------------------------------------
        # Determine whether each side is a server
        # -------------------------------------------------

        local_listening_ports = (
            listening_ports_by_container.get(
                local_container["id"],
                set()
            )
        )

        remote_listening_ports = (
            listening_ports_by_container.get(
                remote_container["id"],
                set()
            )
        )

        local_is_server = (
            row["local_port"]
            in local_listening_ports
        )

        remote_is_server = (
            row["remote_port"]
            in remote_listening_ports
        )

        # -------------------------------------------------
        # Determine actual dependency direction
        # -------------------------------------------------

        if (
            remote_is_server
            and not local_is_server
        ):

            # Client-side representation:
            #
            # client:ephemeral
            #        ->
            # server:listening
            #
            source_id = local_id

            destination_id = remote_id

            destination_port = (
                row["remote_port"]
            )

        elif (
            local_is_server
            and not remote_is_server
        ):

            # Server-side representation:
            #
            # server:listening
            #        ->
            # client:ephemeral
            #
            # Reverse it.
            #
            # Final result:
            #
            # client
            #   ->
            # server
            #

            source_id = remote_id

            destination_id = local_id

            destination_port = (
                row["local_port"]
            )

        else:

            # Ambiguous connection.
            #
            # Either both sides look like servers
            # or neither side has a known listening port.
            #
            # Don't invent a dependency.
            continue

        # -------------------------------------------------
        # Deduplicate edges
        # -------------------------------------------------

        key = (
            source_id,
            destination_id,
            destination_port,
        )

        if key not in edges:

            edges[key] = {
                "count": 0,

                "states": set(),

                "protocol": row["proto"],
            }

        edges[key]["count"] += 1

        edges[key]["states"].add(
            row["state"]
        )

    # -----------------------------------------------------
    # Format edges
    # -----------------------------------------------------

    formatted_edges = []

    for (
        source,
        target,
        port
    ), value in edges.items():

        states = value["states"]

        if TCP_ESTABLISHED in states:

            evidence = (
                "docker_exec:/proc/net/tcp:"
                "ESTABLISHED"
            )

        else:

            evidence = (
                "docker_exec:/proc/net/tcp:"
                "TIME_WAIT"
            )

        formatted_edges.append({

            "source": source,

            "target": target,

            "remote_port": port,

            "observed_connections": (
                value["count"]
            ),

            "protocol": value["protocol"],

            "observed_states": sorted(
                states
            ),

            "evidence": evidence,
        })

    # -----------------------------------------------------
    # Sort nodes and edges for stable output
    # -----------------------------------------------------

    for node in nodes.values():

        node[
            "observed_listening_ports"
        ].sort()

    formatted_edges.sort(
        key=lambda edge: (
            edge["source"],
            edge["target"],
            edge["remote_port"],
        )
    )

    # -----------------------------------------------------
    # Final topology
    # -----------------------------------------------------

    return {
        "discovery_method":
            "docker_cli+container_procfs",

        "docker_enrichment_active":
            True,

        "nodes":
            list(nodes.values()),

        "edges":
            formatted_edges,
    }