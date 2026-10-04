from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api", tags=["incident-room"])


def _database_url() -> str:
    return os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/postgres",
    )


def _connect():
    return psycopg.connect(_database_url())


def _json(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    assignee: str | None = Field(default=None, max_length=200)


class TaskUpdate(BaseModel):
    status: str | None = None
    assignee: str | None = Field(default=None, max_length=200)


class CommentCreate(BaseModel):
    author: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)


def _incident_exists(conn, incident_id: UUID) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM incidents WHERE id = %s",
            (incident_id,),
        )
        return cur.fetchone() is not None


def _next_sequence(conn, incident_id: UUID) -> int:
    # Serialize event numbering per incident.
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            (str(incident_id),),
        )
        cur.execute(
            """
            SELECT COALESCE(MAX(sequence), 0) + 1
            FROM incident_events
            WHERE incident_id = %s
            """,
            (incident_id,),
        )
        return int(cur.fetchone()[0])


def _append_event(
    conn,
    incident_id: UUID,
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    event_id = uuid4()
    occurred_at = datetime.now(timezone.utc)
    sequence = _next_sequence(conn, incident_id)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO incident_events
                (id, incident_id, event_id, event_type,
                 sequence, occurred_at, payload)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                uuid4(),
                incident_id,
                event_id,
                event_type,
                sequence,
                occurred_at,
                psycopg.types.json.Jsonb(payload),
            ),
        )

    return {
        "event_id": str(event_id),
        "incident_id": str(incident_id),
        "event_type": event_type,
        "sequence": sequence,
        "occurred_at": occurred_at.isoformat(),
        "payload": payload,
    }


@router.get("/incidents/{incident_id}/tasks")
def list_tasks(incident_id: UUID):
    with _connect() as conn:
        if not _incident_exists(conn, incident_id):
            raise HTTPException(status_code=404, detail="Incident not found")

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, incident_id, title, status,
                       assignee, created_at, completed_at
                FROM tasks
                WHERE incident_id = %s
                ORDER BY created_at ASC
                """,
                (incident_id,),
            )

            rows = cur.fetchall()

    return [
        {
            "task_id": str(row[0]),
            "incident_id": str(row[1]),
            "title": row[2],
            "status": row[3],
            "assignee": row[4],
            "created_at": row[5].isoformat(),
            "completed_at": (
                row[6].isoformat()
                if row[6] is not None
                else None
            ),
        }
        for row in rows
    ]


@router.post("/incidents/{incident_id}/tasks", status_code=201)
def create_task(incident_id: UUID, request: TaskCreate):
    task_id = uuid4()
    now = datetime.now(timezone.utc)

    with _connect() as conn:
        if not _incident_exists(conn, incident_id):
            raise HTTPException(status_code=404, detail="Incident not found")

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tasks
                    (id, incident_id, title, status, assignee, created_at)
                VALUES
                    (%s, %s, %s, 'OPEN', %s, %s)
                """,
                (
                    task_id,
                    incident_id,
                    request.title,
                    request.assignee,
                    now,
                ),
            )

        event = _append_event(
            conn,
            incident_id,
            "TASK_CREATED",
            {
                "task_id": str(task_id),
                "title": request.title,
                "assignee": request.assignee,
                "status": "OPEN",
            },
        )

        conn.commit()

    return {
        "task_id": str(task_id),
        "incident_id": str(incident_id),
        "title": request.title,
        "status": "OPEN",
        "assignee": request.assignee,
        "created_at": now.isoformat(),
        "completed_at": None,
        "event": event,
    }


@router.patch("/tasks/{task_id}")
def update_task(task_id: UUID, request: TaskUpdate):
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT incident_id, title, status, assignee,
                       created_at, completed_at
                FROM tasks
                WHERE id = %s
                """,
                (task_id,),
            )
            row = cur.fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="Task not found")

        incident_id = row[0]
        old_status = row[2]
        new_status = request.status or old_status
        new_assignee = (
            request.assignee
            if request.assignee is not None
            else row[3]
        )

        allowed = {
            "OPEN",
            "IN_PROGRESS",
            "DONE",
        }

        if new_status not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid task status: {new_status}",
            )

        completed_at = row[5]

        if new_status == "DONE":
            completed_at = datetime.now(timezone.utc)
        elif new_status != "DONE":
            completed_at = None

        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tasks
                SET status = %s,
                    assignee = %s,
                    completed_at = %s
                WHERE id = %s
                """,
                (
                    new_status,
                    new_assignee,
                    completed_at,
                    task_id,
                ),
            )

        event = _append_event(
            conn,
            incident_id,
            "TASK_UPDATED",
            {
                "task_id": str(task_id),
                "from_status": old_status,
                "to_status": new_status,
                "assignee": new_assignee,
            },
        )

        conn.commit()

    return {
        "task_id": str(task_id),
        "incident_id": str(incident_id),
        "title": row[1],
        "status": new_status,
        "assignee": new_assignee,
        "created_at": row[4].isoformat(),
        "completed_at": (
            completed_at.isoformat()
            if completed_at
            else None
        ),
        "event": event,
    }


@router.get("/incidents/{incident_id}/comments")
def list_comments(incident_id: UUID):
    with _connect() as conn:
        if not _incident_exists(conn, incident_id):
            raise HTTPException(status_code=404, detail="Incident not found")

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, incident_id, author, body, created_at
                FROM comments
                WHERE incident_id = %s
                ORDER BY created_at ASC
                """,
                (incident_id,),
            )

            rows = cur.fetchall()

    return [
        {
            "comment_id": str(row[0]),
            "incident_id": str(row[1]),
            "author": row[2],
            "body": row[3],
            "created_at": row[4].isoformat(),
        }
        for row in rows
    ]


@router.post("/incidents/{incident_id}/comments", status_code=201)
def create_comment(
    incident_id: UUID,
    request: CommentCreate,
):
    comment_id = uuid4()
    now = datetime.now(timezone.utc)

    with _connect() as conn:
        if not _incident_exists(conn, incident_id):
            raise HTTPException(status_code=404, detail="Incident not found")

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO comments
                    (id, incident_id, author, body, created_at)
                VALUES
                    (%s, %s, %s, %s, %s)
                """,
                (
                    comment_id,
                    incident_id,
                    request.author,
                    request.body,
                    now,
                ),
            )

        event = _append_event(
            conn,
            incident_id,
            "COMMENT_ADDED",
            {
                "comment_id": str(comment_id),
                "author": request.author,
                "body": request.body,
            },
        )

        conn.commit()

    return {
        "comment_id": str(comment_id),
        "incident_id": str(incident_id),
        "author": request.author,
        "body": request.body,
        "created_at": now.isoformat(),
        "event": event,
    }
