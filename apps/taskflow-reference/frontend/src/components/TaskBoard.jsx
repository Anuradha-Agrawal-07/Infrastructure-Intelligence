import { useEffect, useState } from "react";
import { api } from "../api.js";

const STATUS_LABELS = {
  todo: "To Do",
  in_progress: "In Progress",
  done: "Done",
};

export default function TaskBoard({ currentUser, users, onTasksChanged }) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ title: "", description: "", assignee_id: "" });
  const [submitting, setSubmitting] = useState(false);

  async function loadTasks() {
    setLoading(true);
    setError("");
    try {
      const data = await api.listTasks();
      setTasks(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadTasks();
  }, []);

  function usernameFor(userId) {
    const u = users.find((u) => u.id === userId);
    return u ? u.username : `user #${userId}`;
  }

  async function handleCreate(e) {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await api.createTask({
        title: form.title,
        description: form.description || undefined,
        assignee_id: form.assignee_id ? Number(form.assignee_id) : undefined,
      });
      setForm({ title: "", description: "", assignee_id: "" });
      setShowForm(false);
      await loadTasks();
      onTasksChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleStatusChange(task, status) {
    try {
      await api.updateTask(task.id, { status });
      await loadTasks();
      onTasksChanged();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleReassign(task, assigneeId) {
    try {
      await api.updateTask(task.id, { assignee_id: assigneeId ? Number(assigneeId) : null });
      await loadTasks();
      onTasksChanged();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleDelete(task) {
    if (!confirm(`Delete task "${task.title}"?`)) return;
    try {
      await api.deleteTask(task.id);
      await loadTasks();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="task-board">
      <div className="board-header">
        <h2>Tasks</h2>
        <button className="primary" onClick={() => setShowForm((s) => !s)}>
          {showForm ? "Cancel" : "+ New Task"}
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      {showForm && (
        <form className="task-form" onSubmit={handleCreate}>
          <input
            placeholder="Task title"
            value={form.title}
            onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            required
          />
          <textarea
            placeholder="Description (optional)"
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
          />
          <select
            value={form.assignee_id}
            onChange={(e) => setForm((f) => ({ ...f, assignee_id: e.target.value }))}
          >
            <option value="">Unassigned</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.username}
              </option>
            ))}
          </select>
          <button className="primary" type="submit" disabled={submitting}>
            {submitting ? "Creating..." : "Create Task"}
          </button>
        </form>
      )}

      {loading ? (
        <p>Loading tasks...</p>
      ) : tasks.length === 0 ? (
        <p className="empty-state">No tasks yet. Create the first one above.</p>
      ) : (
        <div className="task-list">
          {tasks.map((task) => (
            <div key={task.id} className={`task-card status-${task.status}`}>
              <div className="task-card-top">
                <h3>{task.title}</h3>
                <span className={`badge badge-${task.status}`}>{STATUS_LABELS[task.status]}</span>
              </div>
              {task.description && <p className="task-desc">{task.description}</p>}
              <div className="task-meta">
                <span>Created by {usernameFor(task.created_by)}</span>
                <span>&middot;</span>
                <label>
                  Assignee:{" "}
                  <select
                    value={task.assignee_id || ""}
                    onChange={(e) => handleReassign(task, e.target.value)}
                  >
                    <option value="">Unassigned</option>
                    {users.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.username}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="task-actions">
                {Object.keys(STATUS_LABELS).map((s) => (
                  <button
                    key={s}
                    className={s === task.status ? "status-btn active" : "status-btn"}
                    onClick={() => handleStatusChange(task, s)}
                  >
                    {STATUS_LABELS[s]}
                  </button>
                ))}
                {task.created_by === currentUser.id && (
                  <button className="danger" onClick={() => handleDelete(task)}>
                    Delete
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
