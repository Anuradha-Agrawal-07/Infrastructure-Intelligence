const API = window.location.origin;
const WS_BASE =
    window.location.protocol === "https:"
        ? "wss://"
        : "ws://";

const WS_URL_BASE =
    WS_BASE + window.location.host;

const state = {
    incidents: [],
    selected: null,
    timeline: [],
    tasks: [],
    comments: [],
    socket: null,
    reconnectTimer: null,
    lastSequence: 0,
    reconnectDelay: 1000,
};

const $ = (id) => document.getElementById(id);

function showToast(message) {
    const toast = $("toast");
    toast.textContent = message;
    toast.classList.add("show");

    setTimeout(() => {
        toast.classList.remove("show");
    }, 2200);
}

async function api(path, options = {}) {
    const response = await fetch(API + path, {
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {}),
        },
        ...options,
    });

    if (!response.ok) {
        let detail = `HTTP ${response.status}`;

        try {
            const body = await response.json();
            detail = body.detail || body.error || detail;
        } catch (_) {}

        throw new Error(detail);
    }

    if (response.status === 204) {
        return null;
    }

    return response.json();
}

function normalizeIncident(raw) {
    return {
        ...raw,
        incident_id: raw.incident_id || raw.id,
        title: raw.title || "Untitled incident",
        status: raw.status || "DETECTED",
        priority: raw.priority || "P2",
        version: raw.version || 1,
        affected_services:
            raw.affected_services ||
            raw.affectedServices ||
            [],
        primary_suspect:
            raw.primary_suspect ||
            raw.primarySuspect ||
            "—",
        confidence:
            raw.confidence ??
            raw.rca_confidence ??
            null,
        blast_radius:
            raw.blast_radius ??
            raw.impact?.blast_radius ??
            null,
        business_capability:
            raw.business_capability ||
            raw.impact?.business_capability ||
            "—",
    };
}

async function loadIncidents() {
    const params = new URLSearchParams();

    if ($("statusFilter").value) {
        params.set("status", $("statusFilter").value);
    }

    if ($("priorityFilter").value) {
        params.set("priority", $("priorityFilter").value);
    }

    const query = params.toString();

    const data = await api(
        "/api/incidents" + (query ? "?" + query : "")
    );

    const list = Array.isArray(data)
        ? data
        : data.incidents || data.items || [];

    state.incidents = list.map(normalizeIncident);

    renderIncidentList();

    if (
        state.selected &&
        !state.incidents.some(
            x => x.incident_id === state.selected.incident_id
        )
    ) {
        state.selected = null;
        $("incidentRoom").classList.add("hidden");
        $("emptyRoom").classList.remove("hidden");
    }
}

function renderIncidentList() {
    const root = $("incidentList");

    if (!state.incidents.length) {
        root.innerHTML =
            '<div class="empty">No incidents found.</div>';
        return;
    }

    root.innerHTML = state.incidents
        .map(incident => {
            const selected =
                state.selected &&
                state.selected.incident_id === incident.incident_id
                    ? "selected"
                    : "";

            return `
                <div
                    class="incident-item ${selected}"
                    data-id="${incident.incident_id}"
                >
                    <div class="incident-item-title">
                        ${escapeHtml(incident.title)}
                    </div>

                    <div class="incident-item-meta">
                        <span>${incident.priority}</span>
                        <span>${incident.status}</span>
                    </div>
                </div>
            `;
        })
        .join("");

    root.querySelectorAll(".incident-item").forEach(item => {
        item.addEventListener("click", () => {
            openIncident(item.dataset.id);
        });
    });
}

async function openIncident(id) {
    try {
        disconnectSocket();

        const incident = normalizeIncident(
            await api(`/api/incidents/${id}`)
        );

        state.selected = incident;
        state.timeline = [];
        state.tasks = [];
        state.comments = [];
        state.lastSequence = 0;

        $("emptyRoom").classList.add("hidden");
        $("incidentRoom").classList.remove("hidden");

        renderIncident();
        renderIncidentList();

        await Promise.all([
            loadTimeline(),
            loadTasks(),
            loadComments(),
        ]);

        connectSocket();

    } catch (error) {
        showToast(error.message);
    }
}

function renderIncident() {
    const incident = state.selected;

    if (!incident) return;

    $("incidentTitle").textContent = incident.title;
    $("incidentId").textContent = incident.incident_id;

    $("priorityBadge").textContent = incident.priority;
    $("statusBadge").textContent = incident.status;

    $("primarySuspect").textContent =
        incident.primary_suspect || "—";

    $("confidence").textContent =
        incident.confidence == null
            ? "—"
            : `${Math.round(incident.confidence * 100)}%`;

    $("blastRadius").textContent =
        incident.blast_radius == null
            ? "—"
            : `${Math.round(incident.blast_radius * 100)}%`;

    $("businessCapability").textContent =
        incident.business_capability || "—";

    const services =
        incident.affected_services || [];

    $("services").innerHTML = services.length
        ? services
            .map(s =>
                `<span class="service">${escapeHtml(s)}</span>`
            )
            .join("")
        : '<span class="empty">No affected services reported.</span>';

    const transitions = {
        DETECTED: ["ACKNOWLEDGED", "FALSE_POSITIVE"],
        ACKNOWLEDGED: ["TRIAGED"],
        TRIAGED: ["INVESTIGATING"],
        INVESTIGATING: ["MITIGATING"],
        MITIGATING: ["RECOVERY_VERIFY"],
        RECOVERY_VERIFY: ["RESOLVED"],
        RESOLVED: ["REOPENED"],
        FALSE_POSITIVE: ["RESOLVED"],
        REOPENED: ["INVESTIGATING"],
    };

    const next = transitions[incident.status] || [];

    $("statusSelect").innerHTML =
        next.length
            ? next
                .map(s => `<option value="${s}">${s}</option>`)
                .join("")
            : '<option value="">No transition</option>';

    $("applyStatus").disabled = next.length === 0;
}

async function loadTimeline() {
    if (!state.selected) return;

    const data = await api(
        `/api/incidents/${state.selected.incident_id}/timeline`
    );

    state.timeline =
        Array.isArray(data)
            ? data
            : data.timeline || data.items || [];

    state.lastSequence = state.timeline.reduce(
        (max, event) =>
            Math.max(max, Number(event.sequence || 0)),
        0
    );

    renderTimeline();
}

function renderTimeline() {
    $("sequenceLabel").textContent =
        `Sequence ${state.lastSequence}`;

    if (!state.timeline.length) {
        $("timeline").innerHTML =
            '<div class="empty">No events yet.</div>';
        return;
    }

    $("timeline").innerHTML =
        state.timeline
            .sort(
                (a, b) =>
                    Number(a.sequence || 0) -
                    Number(b.sequence || 0)
            )
            .map(event => `
                <div class="timeline-item">
                    <div class="timeline-line"></div>

                    <div class="timeline-content">
                        <div class="timeline-type">
                            #${event.sequence ?? "—"}
                            ${escapeHtml(
                                event.event_type ||
                                event.type ||
                                "EVENT"
                            )}
                        </div>

                        <div class="timeline-time">
                            ${formatTime(
                                event.occurred_at ||
                                event.created_at
                            )}
                        </div>

                        <div class="timeline-payload">
                            ${escapeHtml(
                                JSON.stringify(
                                    event.payload || {},
                                    null,
                                    2
                                )
                            )}
                        </div>
                    </div>
                </div>
            `)
            .join("");
}

async function loadTasks() {
    if (!state.selected) return;

    state.tasks = await api(
        `/api/incidents/${state.selected.incident_id}/tasks`
    );

    renderTasks();
}

function renderTasks() {
    if (!state.tasks.length) {
        $("tasks").innerHTML =
            '<div class="empty">No investigation tasks.</div>';
        return;
    }

    $("tasks").innerHTML =
        state.tasks
            .map(task => `
                <div class="task">
                    <div class="task-main">
                        <div class="task-title">
                            ${escapeHtml(task.title)}
                        </div>

                        <div class="status">
                            ${escapeHtml(task.status)}
                        </div>
                    </div>

                    <div class="task-meta">
                        Assignee:
                        ${escapeHtml(task.assignee || "Unassigned")}
                    </div>

                    <div class="task-actions">
                        ${
                            task.status !== "IN_PROGRESS"
                                ? `<button
                                    class="small-btn"
                                    onclick="updateTask('${task.task_id}','IN_PROGRESS')"
                                   >
                                    Start
                                   </button>`
                                : ""
                        }

                        ${
                            task.status !== "DONE"
                                ? `<button
                                    class="small-btn"
                                    onclick="updateTask('${task.task_id}','DONE')"
                                   >
                                    Complete
                                   </button>`
                                : ""
                        }
                    </div>
                </div>
            `)
            .join("");
}

async function updateTask(taskId, status) {
    try {
        await api(`/api/tasks/${taskId}`, {
            method: "PATCH",
            body: JSON.stringify({ status }),
        });

        await loadTasks();
        await loadTimeline();

        showToast("Task updated");
    } catch (error) {
        showToast(error.message);
    }
}

async function loadComments() {
    if (!state.selected) return;

    state.comments = await api(
        `/api/incidents/${state.selected.incident_id}/comments`
    );

    renderComments();
}

function renderComments() {
    if (!state.comments.length) {
        $("comments").innerHTML =
            '<div class="empty">No investigator comments.</div>';
        return;
    }

    $("comments").innerHTML =
        state.comments
            .map(comment => `
                <div class="comment">
                    <div class="comment-head">
                        <span class="comment-author">
                            ${escapeHtml(comment.author)}
                        </span>

                        <span>
                            ${formatTime(comment.created_at)}
                        </span>
                    </div>

                    <div class="comment-body">
                        ${escapeHtml(comment.body)}
                    </div>
                </div>
            `)
            .join("");
}

async function connectSocket() {
    if (!state.selected) return;

    const id = state.selected.incident_id;

    try {
        const socket = new WebSocket(
            `${WS_URL_BASE}/ws/incidents/${id}`
        );

        state.socket = socket;

        socket.onopen = () => {
            state.reconnectDelay = 1000;

            $("wsDot").className = "dot online";
            $("wsStatus").textContent = "Live";

            socket.send(
                JSON.stringify({
                    type: "SUBSCRIBE",
                    incident_id: id,
                    last_sequence: state.lastSequence,
                })
            );
        };

        socket.onmessage = async event => {
            try {
                const message = JSON.parse(event.data);

                if (message.type === "EVENT") {
                    const sequence =
                        Number(message.sequence || 0);

                    if (
                        sequence &&
                        sequence <= state.lastSequence
                    ) {
                        return;
                    }

                    state.lastSequence = Math.max(
                        state.lastSequence,
                        sequence
                    );

                    state.timeline.push({
                        event_id: message.event_id,
                        event_type: message.event_type,
                        incident_id: message.incident_id,
                        sequence,
                        occurred_at:
                            message.server_time ||
                            new Date().toISOString(),
                        payload: message.payload || {},
                    });

                    renderTimeline();

                    await refreshIncidentFromEvent(
                        message.event_type
                    );
                }

                if (message.type === "CATCH_UP_COMPLETE") {
                    showToast("Timeline caught up");
                }
            } catch (_) {}
        };

        socket.onclose = () => {
            if (state.socket !== socket) return;

            $("wsDot").className = "dot offline";
            $("wsStatus").textContent = "Reconnecting...";

            clearTimeout(state.reconnectTimer);

            state.reconnectTimer = setTimeout(() => {
                if (state.selected) {
                    connectSocket();
                }
            }, state.reconnectDelay);

            state.reconnectDelay = Math.min(
                state.reconnectDelay * 2,
                10000
            );
        };

        socket.onerror = () => {
            $("wsDot").className = "dot offline";
            $("wsStatus").textContent = "Connection error";
        };

    } catch (_) {
        $("wsDot").className = "dot offline";
        $("wsStatus").textContent = "Disconnected";
    }
}

async function refreshIncidentFromEvent(type) {
    if (!state.selected) return;

    if (
        type === "INCIDENT_STATUS_CHANGED" ||
        type === "TASK_CREATED" ||
        type === "TASK_UPDATED" ||
        type === "COMMENT_ADDED"
    ) {
        try {
            state.selected = normalizeIncident(
                await api(
                    `/api/incidents/${state.selected.incident_id}`
                )
            );

            renderIncident();
            renderIncidentList();

            if (
                type === "TASK_CREATED" ||
                type === "TASK_UPDATED"
            ) {
                await loadTasks();
            }

            if (type === "COMMENT_ADDED") {
                await loadComments();
            }
        } catch (_) {}
    }
}

function disconnectSocket() {
    clearTimeout(state.reconnectTimer);

    if (state.socket) {
        const socket = state.socket;
        state.socket = null;

        try {
            socket.close();
        } catch (_) {}
    }

    $("wsDot").className = "dot offline";
    $("wsStatus").textContent = "Disconnected";
}

async function changeStatus() {
    if (!state.selected) return;

    const status = $("statusSelect").value;

    if (!status) return;

    try {
        const updated = await api(
            `/api/incidents/${state.selected.incident_id}/status`,
            {
                method: "PATCH",
                body: JSON.stringify({
                    status,
                    expected_version: state.selected.version,
                }),
            }
        );

        state.selected = normalizeIncident(updated);

        renderIncident();
        renderIncidentList();

        await loadTimeline();

        showToast(`Incident → ${status}`);
    } catch (error) {
        showToast(error.message);

        // Refresh on version conflict / concurrent update.
        try {
            state.selected = normalizeIncident(
                await api(
                    `/api/incidents/${state.selected.incident_id}`
                )
            );

            renderIncident();
            await loadTimeline();
        } catch (_) {}
    }
}

async function createTask(event) {
    event.preventDefault();

    if (!state.selected) return;

    const title = $("taskTitle").value.trim();
    const assignee = $("taskAssignee").value.trim();

    if (!title) return;

    try {
        await api(
            `/api/incidents/${state.selected.incident_id}/tasks`,
            {
                method: "POST",
                body: JSON.stringify({
                    title,
                    assignee: assignee || null,
                }),
            }
        );

        $("taskTitle").value = "";
        $("taskAssignee").value = "";

        await loadTasks();
        await loadTimeline();

        showToast("Task created");
    } catch (error) {
        showToast(error.message);
    }
}

async function createComment(event) {
    event.preventDefault();

    if (!state.selected) return;

    const author = $("commentAuthor").value.trim();
    const body = $("commentBody").value.trim();

    if (!author || !body) return;

    try {
        await api(
            `/api/incidents/${state.selected.incident_id}/comments`,
            {
                method: "POST",
                body: JSON.stringify({
                    author,
                    body,
                }),
            }
        );

        $("commentBody").value = "";

        await loadComments();
        await loadTimeline();

        showToast("Comment added");
    } catch (error) {
        showToast(error.message);
    }
}

function formatTime(value) {
    if (!value) return "—";

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return String(value);
    }

    return date.toLocaleString();
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

$("refreshBtn").addEventListener(
    "click",
    () => loadIncidents().catch(e => showToast(e.message))
);

$("statusFilter").addEventListener(
    "change",
    () => loadIncidents().catch(e => showToast(e.message))
);

$("priorityFilter").addEventListener(
    "change",
    () => loadIncidents().catch(e => showToast(e.message))
);

$("applyStatus").addEventListener(
    "click",
    changeStatus
);

$("taskForm").addEventListener(
    "submit",
    createTask
);

$("commentForm").addEventListener(
    "submit",
    createComment
);

window.updateTask = updateTask;

loadIncidents().catch(error => {
    $("incidentList").innerHTML =
        `<div class="empty">${escapeHtml(error.message)}</div>`;
    showToast(error.message);
});
