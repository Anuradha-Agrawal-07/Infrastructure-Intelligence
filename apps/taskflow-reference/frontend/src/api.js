// All requests from the browser go to the API Gateway only. The gateway is
// responsible for talking to auth-service, task-service, and
// notification-service. The frontend never calls those services directly.
const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

function getToken() {
  return localStorage.getItem("pm_token");
}

function setToken(token) {
  if (token) {
    localStorage.setItem("pm_token", token);
  } else {
    localStorage.removeItem("pm_token");
  }
}

async function request(path, { method = "GET", body, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  const resp = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (resp.status === 204) return null;

  const text = await resp.text();
  const data = text ? JSON.parse(text) : null;

  if (!resp.ok) {
    const detail = (data && data.detail) || resp.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  return data;
}

export const api = {
  register: (payload) => request("/api/auth/register", { method: "POST", body: payload, auth: false }),
  login: (payload) => request("/api/auth/login", { method: "POST", body: payload, auth: false }),
  me: () => request("/api/users/me"),
  listUsers: () => request("/api/users"),
  listTasks: (assigneeId) =>
    request(`/api/tasks${assigneeId ? `?assignee_id=${assigneeId}` : ""}`),
  createTask: (payload) => request("/api/tasks", { method: "POST", body: payload }),
  updateTask: (id, payload) => request(`/api/tasks/${id}`, { method: "PATCH", body: payload }),
  deleteTask: (id) => request(`/api/tasks/${id}`, { method: "DELETE" }),
  listNotifications: () => request("/api/notifications"),
  getToken,
  setToken,
};
