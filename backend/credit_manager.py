from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from models import User, CreditHistory


async def reset_monthly_free_credits(db: AsyncSession, user: User):
    """
    Reset monthly free credits if a new month has started.
    """
    if user.last_free_credit_reset is None:
        user.last_free_credit_reset = datetime.now()
        return
    
    # Check if it's a new month
    now = datetime.now()
    last_reset = user.last_free_credit_reset
    
    if now.year > last_reset.year or (now.year == last_reset.year and now.month > last_reset.month):
        # New month - reset the counter
        user.free_credits_used_this_month = 0
        user.last_free_credit_reset = now
        await db.commit()


async def add_daily_subscription_credits(db: AsyncSession, user: User):
    """
    Add daily subscription credits if subscription is active and it's a new day.
    """
    if not user.subscription_active:
        return
    
    # Check if subscription has expired
    if user.subscription_end_date and datetime.now() > user.subscription_end_date:
        user.subscription_active = False
        await db.commit()
        return
    
    # Check if we need to add today's credits
    now = datetime.now()
    last_credit_date = user.last_daily_credit_date
    
    if last_credit_date is None or last_credit_date.date() < now.date():
        # New day - add subscription credits
        credits_to_add = user.subscription_credits_per_day
        user.credits += credits_to_add
        user.last_daily_credit_date = now
        
        # Log to history
        db.add(CreditHistory(
            user_id=user.id,
            reason=f"Daily Subscription Credits - {credits_to_add} credits",
            credits_change_instant=credits_to_add,
            balance_after_instant=user.credits
        ))
        
        await db.commit()


async def deduct_credits(db: AsyncSession, user: User, amount: int, reason: str = "Email Verification"):
    """
    Deduct credits from user account with proper logging.
    
    Args:
        db: Database session
        user: User object
        amount: Number of credits to deduct
        reason: Reason for deduction (for logging)
    
    Raises:
        ValueError: If user has insufficient credits
    """
    if user.credits < amount:
        raise ValueError("Insufficient credits")
    
    old_balance = user.credits
    user.credits -= amount
    
    # Track free credits usage if applicable
    if hasattr(user, 'free_credits_used_this_month'):
        user.free_credits_used_this_month += amount
    
    # Log to history
    db.add(CreditHistory(
        user_id=user.id,
        reason=reason,
        credits_change_instant=-amount,
        balance_after_instant=user.credits
    ))
    
    await db.commit()


async def process_all_users_credits(db: AsyncSession):
    """
    Process credits for all users - called by scheduler daily.
    This function:
    1. Adds daily subscription credits for active subscribers
    2. Resets monthly free credits at the start of each month
    """
    from sqlalchemy import select
    
    # Get all users
    result = await db.execute(select(User))
    users = result.scalars().all()
    
    now = datetime.now()
    
    for user in users:
        try:
            # Reset monthly free credits if needed
            await reset_monthly_free_credits(db, user)
            
            # Add daily subscription credits if needed
            await add_daily_subscription_credits(db, user)
            
        except Exception as e:
            print(f"Error processing credits for user {user.id}: {str(e)}")
            continue
    
    await db.commit()
    print(f"✅ Processed credits for {len(users)} users at {now}")