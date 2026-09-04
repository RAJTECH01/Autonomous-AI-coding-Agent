from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from enum import Enum


class UserRole(str, Enum):
    ADMINISTRATOR = "administrator"
    ADMIN = "admin"
    USER = "user"
    DEVELOPER = "developer"
    VIEWER = "viewer"


@dataclass
class User:
    id: str
    email: str
    password_hash: str
    full_name: str
    role: UserRole = UserRole.USER
    is_active: bool = True
    is_verified: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
