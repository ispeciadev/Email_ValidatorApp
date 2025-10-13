# utils/credits.py
from datetime import date, datetime
import models
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError


async def ensure_daily_reset(db: AsyncSession, user: models.User):
    """
    Reset daily credits if last reset is not today.
    This ensures each user gets their daily quota every day.
    """
    today = date.today()

    # Use last_daily_reset from your User model
    if not user.last_daily_reset or user.last_daily_reset.date() != today:
        user.daily_credits = user.daily_quota_limit  # reset daily credits
        user.last_daily_reset = datetime.utcnow()

        try:
            db.add(user)
            await db.commit()
            await db.refresh(user)
        except SQLAlchemyError:
            await db.rollback()

    return user


async def buy_credits(
    db: AsyncSession, user: models.User, amount: int, credit_type: str = "total"
) -> models.User:
    """
    Buy credits and add them to the user's account.
    credit_type can be:
      - 'total' -> add to total credits only (default Pay-As-You-Go)
      - 'instant' -> add to instant credits (for immediate use)
    """
    if amount <= 0:
        raise ValueError("Amount must be greater than 0")

    if credit_type == "instant":
        user.instant_credits += amount
    else:  # default pay-as-you-go
        user.total_credits += amount

    # Always keep total consistent
    user.total_credits = user.daily_credits + user.instant_credits

    try:
        db.add(user)
        await db.commit()
        await db.refresh(user)
    except SQLAlchemyError as e:
        await db.rollback()
        raise ValueError(f"Failed to update credits: {str(e)}")

    return user


async def use_credits(
    db: AsyncSession, user: models.User, count: int, prefer: str = "auto"
) -> models.User:
    """
    Deduct credits from user account.
    prefer options:
      - 'daily' -> try to use daily credits first
      - 'instant' -> use instant credits first
      - 'auto' -> use daily if available, then instant, then total
    """
    if count <= 0:
        raise ValueError("Count must be greater than 0")

    # Ensure daily reset first
    user = await ensure_daily_reset(db, user)

    remaining = count

    if prefer == "daily":
        if user.daily_credits >= remaining:
            user.daily_credits -= remaining
            remaining = 0
        else:
            remaining -= user.daily_credits
            user.daily_credits = 0

    elif prefer == "instant":
        if user.instant_credits >= remaining:
            user.instant_credits -= remaining
            remaining = 0
        else:
            remaining -= user.instant_credits
            user.instant_credits = 0

    elif prefer == "auto":
        # Deduct from daily first
        if user.daily_credits >= remaining:
            user.daily_credits -= remaining
            remaining = 0
        else:
            remaining -= user.daily_credits
            user.daily_credits = 0

        # Deduct from instant next
        if remaining > 0:
            if user.instant_credits >= remaining:
                user.instant_credits -= remaining
                remaining = 0
            else:
                remaining -= user.instant_credits
                user.instant_credits = 0

    # Finally, deduct from total credits if any remaining
    if remaining > 0:
        if user.total_credits >= remaining:
            user.total_credits -= remaining
            remaining = 0
        else:
            raise ValueError("Not enough credits to complete the operation")

    # Keep total consistent
    user.total_credits = user.daily_credits + user.instant_credits

    try:
        db.add(user)
        await db.commit()
        await db.refresh(user)
    except SQLAlchemyError as e:
        await db.rollback()
        raise ValueError(f"Failed to use credits: {str(e)}")

    return user
