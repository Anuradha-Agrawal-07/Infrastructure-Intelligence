import logging

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from . import models, schemas
from .database import Base, engine, get_db, wait_for_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("task-service")

app = FastAPI(title="Task Service", version="1.0.0")


@app.on_event("startup")
def on_startup() -> None:
    logger.info("task-service starting up, waiting for PostgreSQL...")
    wait_for_db()
    Base.metadata.create_all(bind=engine)
    logger.info("task-service ready, tasks table ensured in PostgreSQL")


@app.get("/health")
def health():
    return {"service": "task-service", "status": "ok"}


@app.post("/tasks", response_model=schemas.TaskOut, status_code=201)
def create_task(payload: schemas.TaskCreate, db: Session = Depends(get_db)):
    task = models.Task(
        title=payload.title,
        description=payload.description,
        assignee_id=payload.assignee_id,
        created_by=payload.created_by,
        status=models.TaskStatus.todo,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    logger.info("created task id=%s assignee_id=%s", task.id, task.assignee_id)
    return task


@app.get("/tasks", response_model=list[schemas.TaskOut])
def list_tasks(assignee_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(models.Task)
    if assignee_id is not None:
        query = query.filter(models.Task.assignee_id == assignee_id)
    return query.order_by(models.Task.created_at.desc()).all()


@app.get("/tasks/{task_id}", response_model=schemas.TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@app.patch("/tasks/{task_id}", response_model=schemas.TaskOut)
def update_task(task_id: int, payload: schemas.TaskUpdate, db: Session = Depends(get_db)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="task not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)

    db.commit()
    db.refresh(task)
    logger.info("updated task id=%s fields=%s", task.id, list(update_data.keys()))
    return task


@app.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    db.delete(task)
    db.commit()
    return None
