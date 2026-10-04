import logging
import os

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import schemas
from .deps import AUTH_SERVICE_URL, get_current_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api-gateway")

TASK_SERVICE_URL = os.environ.get("TASK_SERVICE_URL", "http://task-service:8002")
NOTIFICATION_SERVICE_URL = os.environ.get("NOTIFICATION_SERVICE_URL", "http://notification-service:8003")

app = FastAPI(title="API Gateway", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"service": "api-gateway", "status": "ok"}


async def _forward(method: str, url: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.request(method, url, **kwargs)
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"upstream service unreachable: {exc}") from exc
    return resp


def _raise_for_upstream(resp: httpx.Response):
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)


# ---------------------------------------------------------------------------
# Auth/User routes  ->  API Gateway  ->  Auth/User Service  ->  PostgreSQL
# ---------------------------------------------------------------------------

@app.post("/api/auth/register", status_code=201)
async def register(payload: schemas.RegisterRequest):
    resp = await _forward("POST", f"{AUTH_SERVICE_URL}/register", json=payload.model_dump())
    _raise_for_upstream(resp)
    logger.info("proxied registration to auth-service, status=%s", resp.status_code)
    return resp.json()


@app.post("/api/auth/login")
async def login(payload: schemas.LoginRequest):
    resp = await _forward("POST", f"{AUTH_SERVICE_URL}/login", json=payload.model_dump())
    _raise_for_upstream(resp)
    logger.info("proxied login to auth-service, status=%s", resp.status_code)
    return resp.json()


@app.get("/api/users")
async def list_users(current_user: dict = Depends(get_current_user)):
    resp = await _forward("GET", f"{AUTH_SERVICE_URL}/users")
    _raise_for_upstream(resp)
    return resp.json()


@app.get("/api/users/me")
async def whoami(current_user: dict = Depends(get_current_user)):
    resp = await _forward("GET", f"{AUTH_SERVICE_URL}/users/{current_user['user_id']}")
    _raise_for_upstream(resp)
    return resp.json()


# ---------------------------------------------------------------------------
# Task routes  ->  API Gateway  ->  Task Service  ->  PostgreSQL
#                            \_->  Notification Service  ->  Redis
# ---------------------------------------------------------------------------

@app.get("/api/tasks")
async def list_tasks(assignee_id: int | None = None, current_user: dict = Depends(get_current_user)):
    params = {"assignee_id": assignee_id} if assignee_id is not None else {}
    resp = await _forward("GET", f"{TASK_SERVICE_URL}/tasks", params=params)
    _raise_for_upstream(resp)
    return resp.json()


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: int, current_user: dict = Depends(get_current_user)):
    resp = await _forward("GET", f"{TASK_SERVICE_URL}/tasks/{task_id}")
    _raise_for_upstream(resp)
    return resp.json()


@app.post("/api/tasks", status_code=201)
async def create_task(payload: schemas.TaskCreateRequest, current_user: dict = Depends(get_current_user)):
    body = payload.model_dump()
    body["created_by"] = current_user["user_id"]

    resp = await _forward("POST", f"{TASK_SERVICE_URL}/tasks", json=body)
    _raise_for_upstream(resp)
    task = resp.json()
    logger.info("created task id=%s via task-service", task["id"])

    if task.get("assignee_id"):
        notif_body = {
            "user_id": task["assignee_id"],
            "type": "task_assigned",
            "message": f"You were assigned a new task: '{task['title']}'",
        }
        notif_resp = await _forward("POST", f"{NOTIFICATION_SERVICE_URL}/notifications", json=notif_body)
        if notif_resp.status_code >= 400:
            logger.warning(
                "task %s created but notification failed: status=%s body=%s",
                task["id"], notif_resp.status_code, notif_resp.text,
            )
        else:
            logger.info("sent assignment notification for task id=%s to user_id=%s", task["id"], task["assignee_id"])

    return task


@app.patch("/api/tasks/{task_id}")
async def update_task(task_id: int, payload: schemas.TaskUpdateRequest, current_user: dict = Depends(get_current_user)):
    existing_resp = await _forward("GET", f"{TASK_SERVICE_URL}/tasks/{task_id}")
    _raise_for_upstream(existing_resp)
    existing_task = existing_resp.json()

    update_body = {k: v for k, v in payload.model_dump().items() if v is not None}
    resp = await _forward("PATCH", f"{TASK_SERVICE_URL}/tasks/{task_id}", json=update_body)
    _raise_for_upstream(resp)
    task = resp.json()
    logger.info("updated task id=%s via task-service, fields=%s", task_id, list(update_body.keys()))

    reassigned = "assignee_id" in update_body and update_body["assignee_id"] != existing_task.get("assignee_id")
    completed = update_body.get("status") == "done" and existing_task.get("status") != "done"

    if reassigned and task.get("assignee_id"):
        notif_body = {
            "user_id": task["assignee_id"],
            "type": "task_assigned",
            "message": f"You were assigned to task: '{task['title']}'",
        }
        await _forward("POST", f"{NOTIFICATION_SERVICE_URL}/notifications", json=notif_body)
        logger.info("sent reassignment notification for task id=%s", task_id)

    if completed:
        notif_body = {
            "user_id": task["created_by"],
            "type": "task_completed",
            "message": f"Task '{task['title']}' was marked done",
        }
        await _forward("POST", f"{NOTIFICATION_SERVICE_URL}/notifications", json=notif_body)
        logger.info("sent completion notification for task id=%s", task_id)

    return task


@app.delete("/api/tasks/{task_id}", status_code=204)
async def delete_task(task_id: int, current_user: dict = Depends(get_current_user)):
    resp = await _forward("DELETE", f"{TASK_SERVICE_URL}/tasks/{task_id}")
    _raise_for_upstream(resp)
    return None


# ---------------------------------------------------------------------------
# Notification routes  ->  API Gateway  ->  Notification Service  ->  Redis
# ---------------------------------------------------------------------------

@app.get("/api/notifications")
async def list_notifications(current_user: dict = Depends(get_current_user)):
    resp = await _forward(
        "GET", f"{NOTIFICATION_SERVICE_URL}/notifications", params={"user_id": current_user["user_id"]}
    )
    _raise_for_upstream(resp)
    return resp.json()
