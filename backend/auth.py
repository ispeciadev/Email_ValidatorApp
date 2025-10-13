from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from models import User as DBUser, EmailRecord  # ✅ Avoid conflict with Pydantic model
from db import get_db
from passlib.hash import bcrypt
from sqlalchemy.future import select
from typing import Literal
import os, json

router = APIRouter()

# JSON path for admin credentials
USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")

# ----- Pydantic Schemas -----
class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: Literal["admin", "user"]

class LoginData(BaseModel):
    email: str
    password: str

# ----- Load admin credentials from JSON -----
def load_admins():
    if not os.path.exists(USERS_FILE):
        return []
    with open(USERS_FILE, "r") as f:
        return json.load(f)

# ----- USER SIGNUP (Database) -----
# ----- USER SIGNUP (Database) -----
@router.post("/signup")
def signup(user: UserCreate, db: Session = Depends(get_db)):
    if user.role == "admin":
        raise HTTPException(status_code=400, detail="Admin signup not allowed")

    existing = db.query(DBUser).filter(DBUser.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    hashed_pwd = bcrypt.hash(user.password)

    # 🎁 Give 50 credits automatically
    new_user = DBUser(
        name=user.name,
        email=user.email,
        hashed_password=hashed_pwd,   # ⚠️ must match your models.py field
        role="user",
        blocked=False,
        status="pending",
        total_credits=50,             # purchased credits
        daily_quota_limit=50,         # daily limit
        daily_credits=50,             # start with 50
        instant_credits=0             # no instant credits at signup
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "message": "Signup successful. Awaiting admin approval.",
        "user_id": new_user.id,
        "email": new_user.email,
        "total_credits": new_user.total_credits,
        "daily_credits": new_user.daily_credits,
    }
