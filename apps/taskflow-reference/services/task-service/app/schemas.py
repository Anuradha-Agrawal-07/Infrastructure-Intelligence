from datetime import datetime

from pydantic import BaseModel, Field

from .models import TaskStatus


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    assignee_id: int | None = None
    created_by: int


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    assignee_id: int | None = None


class TaskOut(BaseModel):
    id: int
    title: str
    description: str | None = None
    status: TaskStatus
    created_by: int
    assignee_id: int | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
