from pydantic import Field

from .base import CamelModel


class LoginIn(CamelModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordIn(CamelModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class UserOut(CamelModel):
    username: str
