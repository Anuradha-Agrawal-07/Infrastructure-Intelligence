import logging

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from . import models, schemas, security
from .database import Base, engine, get_db, wait_for_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auth-service")

app = FastAPI(title="Auth/User Service", version="1.0.0")


@app.on_event("startup")
def on_startup() -> None:
    logger.info("auth-service starting up, waiting for PostgreSQL...")
    wait_for_db()
    Base.metadata.create_all(bind=engine)
    logger.info("auth-service ready, users table ensured in PostgreSQL")


@app.get("/health")
def health():
    return {"service": "auth-service", "status": "ok"}


@app.post("/register", response_model=schemas.UserOut, status_code=201)
def register(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    user = models.User(
        username=payload.username,
        email=payload.email,
        full_name=payload.full_name,
        password_hash=security.hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="username or email already exists")
    db.refresh(user)
    logger.info("registered new user id=%s username=%s", user.id, user.username)
    return user


@app.post("/login", response_model=schemas.TokenOut)
def login(payload: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == payload.username).first()
    if not user or not security.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid username or password")
    token = security.create_access_token(user.id, user.username)
    logger.info("issued token for user id=%s", user.id)
    return schemas.TokenOut(access_token=token, user=user)


@app.post("/verify", response_model=schemas.VerifyResponse)
def verify(payload: schemas.VerifyRequest):
    decoded = security.decode_access_token(payload.token)
    if not decoded:
        return schemas.VerifyResponse(valid=False)
    return schemas.VerifyResponse(
        valid=True,
        user_id=int(decoded["sub"]),
        username=decoded["username"],
    )


@app.get("/users/{user_id}", response_model=schemas.UserOut)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return user


@app.get("/users", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(models.User).order_by(models.User.id).all()
