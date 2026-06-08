from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCredentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AppointmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    event_time: datetime
    priority: int = Field(ge=1, le=5)
    guest_emails: list[EmailStr] = Field(default_factory=list)


class AppointmentUpdate(AppointmentCreate):
    pass


class AppointmentOut(BaseModel):
    id: int
    title: str
    description: str
    event_time: datetime
    priority: int
    guest_emails: list[EmailStr]

    model_config = {"from_attributes": True}
