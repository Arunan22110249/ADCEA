"""Pydantic request schemas for the API."""

from pydantic import BaseModel, EmailStr, Field, validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)

    @validator("email", pre=True)
    def normalize_email(cls, value):
        if isinstance(value, str):
            return value.strip().lower()
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)

    @validator("email", pre=True)
    def normalize_email(cls, value):
        if isinstance(value, str):
            return value.strip().lower()
        return value
