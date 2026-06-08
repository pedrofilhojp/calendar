import logging
import os

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from .auth import create_access_token, get_current_user, hash_password, verify_password
from .database import Base, engine, get_db
from .models import Appointment, User
from .rabbitmq import check_rabbitmq, publish_appointment
from .schemas import AppointmentCreate, AppointmentOut, AppointmentUpdate, TokenResponse, UserCredentials


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
LOGGER = logging.getLogger("agenda.backend")

app = FastAPI(title="Agenda API", version="1.0.0", root_path=os.getenv("ROOT_PATH", ""))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    LOGGER.info("Starting backend and validating database schema")
    Base.metadata.create_all(bind=engine)


@app.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(credentials: UserCredentials, db: Session = Depends(get_db)) -> TokenResponse:
    user = User(email=credentials.email, hashed_password=hash_password(credentials.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="E-mail já cadastrado")
    db.refresh(user)
    return TokenResponse(access_token=create_access_token(user))


@app.post("/auth/login", response_model=TokenResponse)
def login(credentials: UserCredentials, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == credentials.email))
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    return TokenResponse(access_token=create_access_token(user))


@app.get("/appointments", response_model=list[AppointmentOut])
def list_appointments(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Appointment]:
    stmt = (
        select(Appointment)
        .where(Appointment.owner_id == current_user.id)
        .order_by(Appointment.event_time.asc())
    )
    return list(db.scalars(stmt))


@app.post("/appointments", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def create_appointment(
    appointment_in: AppointmentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Appointment:
    appointment = Appointment(
        title=appointment_in.title,
        description=appointment_in.description,
        event_time=appointment_in.event_time,
        priority=appointment_in.priority,
        guest_emails=[str(email) for email in appointment_in.guest_emails],
        owner_id=current_user.id,
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)

    publish_appointment(
        {
            "id": appointment.id,
            "title": appointment.title,
            "description": appointment.description,
            "event_time": appointment.event_time.isoformat(),
            "priority": appointment.priority,
            "guest_emails": appointment.guest_emails,
            "owner_email": current_user.email,
        }
    )
    return appointment


@app.put("/appointments/{appointment_id}", response_model=AppointmentOut)
def update_appointment(
    appointment_id: int,
    appointment_in: AppointmentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Appointment:
    appointment = db.get(Appointment, appointment_id)
    if not appointment or appointment.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Compromisso não encontrado")

    appointment.title = appointment_in.title
    appointment.description = appointment_in.description
    appointment.event_time = appointment_in.event_time
    appointment.priority = appointment_in.priority
    appointment.guest_emails = [str(email) for email in appointment_in.guest_emails]
    db.commit()
    db.refresh(appointment)
    return appointment


@app.delete("/appointments/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_appointment(
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    appointment = db.get(Appointment, appointment_id)
    if not appointment or appointment.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Compromisso não encontrado")
    db.delete(appointment)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/healthz/live")
def live() -> dict:
    return {"status": "alive"}


@app.get("/healthz/ready")
def ready(db: Session = Depends(get_db)) -> dict:
    checks = {"database": False, "rabbitmq": False}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = True
    except SQLAlchemyError:
        LOGGER.exception("Database readiness check failed")

    try:
        checks["rabbitmq"] = check_rabbitmq()
    except Exception:
        LOGGER.exception("RabbitMQ readiness check failed")

    if not all(checks.values()):
        raise HTTPException(status_code=503, detail=checks)
    return {"status": "ready", "checks": checks}
