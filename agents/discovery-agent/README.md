# Infrastructure Discovery Agent

A standalone, reusable agent that automatically discovers the running
services and dependencies of **any** application environment, purely
by observing live runtime state. It is completely separate from any
application it monitors (Nimbus Store or otherwise) and requires zero
changes to that application's code.

## What this is NOT

- Not the monitoring platform, anomaly detection, correlation, or
  root-cause engine — those come later.
- Not a config-file parser. It never reads `services.json`, a
  docker-compose file, or any manually maintained list of services.
- Not eBPF/OBI-based. No kernel modules, no packet capture, no
  privileged tracing infrastructure.
- Not Node/Express-specific. Nothing here assumes any language,
  framework, or web server.

## How discovery works

Every TCP-based service on Linux — regardless of what language wrote
it — is visible through two universal, already-existing, read-only
kernel interfaces:

1. **`/proc/<pid>/net/tcp` and `/tcp6`** — the live socket table for
   that process's network namespace: every LISTENing and ESTABLISHED
   connection, by local/remote IP:port.
2. **`/proc/<pid>/fd/*`** — which process owns which socket (via the
   `socket:[inode]` symlinks), so a row in the socket table can be
   attributed to a real, named process.

The agent combines these into a topology using one identity rule:

> **A "service" is a process that owns a LISTENing socket.** Its port
> is its identity. A dependency edge exists when another process holds
> an ESTABLISHED connection whose *remote* port matches a known
> LISTENing service.

This single rule is what lets the agent handle multi-process apps
(e.g. Postgres, which forks a new backend process per client
connection) without special-casing them: all of Postgres's forked
children still resolve to "the service listening on port 5432,"
because identity is keyed by **port**, not by which specific PID
happens to be handling one particular connection.

### Optional Docker enrichment (never required)

If `/var/run/docker.sock` is reachable, the agent additionally makes
**read-only** GET calls to the Docker API (`/containers/json`,
`/containers/<id>/json`) to translate a container's network IP and
PID into its real name, image, and labels. This only improves labels —
if Docker isn't present, or the target isn't containerized at all, the
exact same procfs-based logic still produces a complete topology,
identifying nodes by process name/cmdline instead. No code path
branches on "is this Node" or "is this Docker" — only on "is richer
metadata available right now."

### Why this generalizes to another application

Nothing in `discovery_agent.py` or `procnet.py` references Nimbus
Store, a port number, a service name, or a framework. The only
apoint of contact with the environment is `/proc` and (optionally)
the Docker socket — both of which exist identically for a Python
Flask app, a Java service, a Go binary, or anything else. Swapping in
a different application means pointing the agent at a different host
process set; no agent code changes.

## Files

```
discovery-agent/
  agent/
    procnet.py          # core passive /proc introspection (no deps)
    docker_meta.py       # optional read-only Docker API enrichment (no deps)
    discovery_agent.py    # ties it together, emits generic topology JSON
  receiver/
    receiver.py           # minimum code to receive + display the topology
  sample_output/
    nimbus_store_topology.json   # real captured output, see below
```

Zero third-party dependencies — pure Python 3 standard library, so the
agent can run anywhere Python 3 runs, alongside or independent of the
application it's observing.

## Output format (generic, no hardcoded topology)

```json
{
  "generated_at": "2026-...",
  "discovery_method": "procfs_sockets" | "procfs_sockets+docker_api",
  "docker_enrichment_active": false,
  "nodes": [
    {
      "id": "process:654",
      "type": "process",
      "name": "node",
      "pid": 654,
      "cmdline": "node src/index.js",
      "env_hints": { "PORT": "4001", "PGHOST": "localhost", "...": "..." },
      "observed_listening_ports": [4001],
      "identified_via": "procfs"
    }
  ],
  "edges": [
    {
      "source": "process:655",
      "target": "process:654",
      "remote_port": 4001,
      "observed_connections": 2,
      "protocol": "tcp",
      "evidence": "proc_net_tcp:ESTABLISHED"
    }
  ]
}
```

When Docker is available, node objects instead look like
`{"id": "container:ab12cd34", "type": "container", "name":
"ii-product-service", "image": "infra-intel-demo-product-service",
"labels": {...}, "networks": [...], ...}` — same shape, richer identity.

## Running it

```bash
# one-shot, print JSON to stdout
python3 agent/discovery_agent.py --pretty

# run continuously and push to a receiver every 10s
python3 agent/discovery_agent.py --interval 10 --post http://localhost:8090/topology

# minimal receiver + viewer
python3 receiver/receiver.py --port 8090
# then open http://localhost:8090/  (plain table view)
#      or   http://localhost:8090/topology  (raw JSON)
```

In a Docker deployment (e.g. Nimbus Store's `docker-compose.yml`), run
the agent as its own container with:
- `/var/run/docker.sock:/var/run/docker.sock:ro` (optional enrichment)
- `pid: host` (so `/proc/<pid>` entries for app containers are visible)
- no network attachment to the app's compose network is required —
  `/proc/<pid>/net/tcp` reflects each process's own namespace
  regardless of which network the agent itself is on.

## Tested on Nimbus Store — proof it's real, not hardcoded

The agent was run against Nimbus Store's actual running processes
(frontend, api-gateway, product-service, order-service, postgres — no
containers were available in this sandbox, so they ran as plain OS
processes, which exercises the identical procfs mechanism Docker
enrichment sits on top of).

**Step 1 — cold start, before any traffic:** running the agent
immediately found all 5 real services from listening sockets alone,
plus two dependency edges that already existed because each backend's
DB connection pool was already open:
`product-service → postgres:5432`, `order-service → postgres:5432`.

**Step 2 — real order placed through the live app:** an actual HTTP
order (`POST /api/orders` via the gateway) was placed for two products
totaling $689.96 (order #34, "Grace Hopper"), while the agent snapshot
was taken mid-flight. It captured a fresh edge:
`order-service → product-service:4001` — the real HTTP call
order-service makes to validate/reserve stock, generated purely by
that request, not declared anywhere in advance.

**Step 3 — sustained traffic, sampled over an interval:** with
continuous requests hitting the gateway, repeated sampling (as the
agent would do with `--interval`) merged into the complete, accurate
dependency graph:

```
curl (client)  →  api-gateway  →  order-service  →  product-service  →  postgres
                                →  product-service ───────────────────────↑
```

This exactly matches Nimbus Store's real architecture — derived
entirely from `/proc`, with `services.json` never read or referenced
by any of this code.

**Step 4 — reusability proof:** without touching a single line of
`discovery_agent.py` or `procnet.py`, the same agent binary was pointed
at a throwaway, unrelated two-process Python stack (a plain
`http.server`-based cache service and a client worker looping
`urllib` requests against it — nothing shared with Nimbus Store, no
Express, no Postgres). The agent correctly discovered both new
processes and, once traffic was sampled, the dependency edge between
them (`worker.py → cache_server.py:9501`) — proving the discovery logic
is generic, not tuned to this one application.

Full captured JSON from the Nimbus Store test is in
`sample_output/nimbus_store_topology.json`.

## Known limitations (by design, for this MVP)

- Docker enrichment couldn't be exercised in this sandbox (no Docker
  daemon available here); the code path is implemented and will
  activate automatically wherever `/var/run/docker.sock` exists — the
  procfs mechanism it enriches was fully validated instead.
- Browser-to-frontend traffic is invisible (correctly so — it never
  touches a container/process this agent can observe), so `frontend`
  appears as a discovered service with no *inbound* edge from a
  container; this is expected and worth surfacing rather than hiding.
- One-shot samples can miss short-lived connections (e.g. an
  HTTP client that doesn't keep-alive); this is why `--interval`
  sampling exists, and matches how any passive observer must behave
  without the app's cooperation.
