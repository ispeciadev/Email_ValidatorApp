from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from models import User, CreditOrder, CreditHistory
from schema import BuyCreditsRequest
from db import get_db
from schema import CreditHistoryOut
from typing import List
router = APIRouter(prefix="/api/credits", tags=["Credits"])

@router.post("/buy")
def buy_credits(request: BuyCreditsRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == request.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 1️⃣ Create Credit Order
    order = CreditOrder(
        userid=user.id,
        credits=request.credits,
        price=request.price,
        plan=request.plan
    )
    db.add(order)

    # 2️⃣ Update User Credits
    if request.plan == "daily":
        user.daily_credits += request.credits
    elif request.plan == "instant":
        user.instant_credits += request.credits
    else:
        raise HTTPException(status_code=400, detail="Invalid plan type")

    # update total credits balance
    user.total_credits = user.daily_credits + user.instant_credits

    # 3️⃣ Add Credit History
    history = CreditHistory(
        user_id=user.id,
        reason="Purchase",
        credits_change_daily=request.credits if request.plan == "daily" else 0,
        credits_change_instant=request.credits if request.plan == "instant" else 0,
        balance_after_daily=user.daily_credits,
        balance_after_instant=user.instant_credits,
    )
    db.add(history)

    # 4️⃣ Save
    db.commit()
    db.refresh(user)
    db.refresh(order)
    db.refresh(history)

    return {
           "order_id": order.id,
    "plan": request.plan,
    "credits_purchased": request.credits,
    "price": request.price,
    "new_balance": {
        "daily": user.daily_credits,
        "instant": user.instant_credits,
        "total": user.total_credits
    },
    "history_id": history.id,
    "message": f"{request.credits} {request.plan} credits added successfully!"
    }
# 🔹 Fetch credit history for a user
@router.get("/history/{user_id}", response_model=List[CreditHistoryOut])
def get_credit_history(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    history = (
        db.query(CreditHistory)
        .filter(CreditHistory.user_id == user_id)
        .order_by(CreditHistory.created_at.desc())
        .all()
    )
    return history