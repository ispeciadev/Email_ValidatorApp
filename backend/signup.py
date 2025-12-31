from fastapi import APIRouter, HTTPException, Depends
from db import get_db
from models import User
from schema import UserCreate
from pydantic import BaseModel, EmailStr
import bcrypt
# from passlib.context import CryptContext
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class UserSignup(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = "user"

@router.post("/signup")
async def signup(user: UserSignup, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == user.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    # hashed_password = pwd_context.hash(user.password)
    # Use bcrypt directly to match main.py and avoid passlib issues
    password_bytes = user.password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password_bytes, salt).decode('utf-8')

    new_user = User(
        name=user.name,
        email=user.email,
        hashed_password=hashed_password,
        role=user.role,
        status="active",
        blocked=False,
        credits=20  # Add this line - set default credits
    )

    try:
        db.add(new_user)
        await db.commit()
        return {"message": "Signup successful! You can now login."}
    except Exception as e:
        await db.rollback()
        import traceback
        traceback.print_exc()
        print(f"ERROR: SIGNUP ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))