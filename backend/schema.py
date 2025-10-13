from pydantic import BaseModel, EmailStr, Field
from typing import Literal
from datetime import datetime

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = "user"


class CreditsOut(BaseModel):
    id: int
    email: EmailStr
    total_credits: int
    daily_credits: int
    daily_quota_limit: int
    instant_credits: int

    model_config = {
        "from_attributes": True
    }  
class BuyCreditsIn(BaseModel):
    amount: int = Field(gt=0)


class UseCreditsIn(BaseModel):
    count: int = Field(gt=0)
    prefer: Literal["auto", "instant", "daily", "total"] = "auto"

class BuyCreditsRequest(BaseModel):
    user_id: int
    credits: int
    price: float
    plan: str  # "daily" or "instant"

class CreditHistoryOut(BaseModel):
    id: int
    reason: str
    credits_change_daily: int
    credits_change_instant: int
    balance_after_daily: int
    balance_after_instant: int
    created_at: datetime

    class Config:
        orm_mode = True