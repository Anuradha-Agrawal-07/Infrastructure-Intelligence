import enum

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text, func

from .database import Base


class TaskStatus(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.todo)
    created_by = Column(Integer, nullable=False)  # user id, from auth-service
    assignee_id = Column(Integer, nullable=True)  # user id, from auth-service
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
