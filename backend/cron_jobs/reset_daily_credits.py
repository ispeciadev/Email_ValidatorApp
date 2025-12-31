import asyncio
from datetime import datetime, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from models import User, UserSubscription, CreditHistory
from db import SessionLocal

async def reset_daily_credits():
    """Reset credits for all users with active subscriptions"""
    print(f"\n{'='*60}")
    print(f"🔄 DAILY CREDIT RESET - {datetime.utcnow().isoformat()}")
    print(f"{'='*60}")
    
    async with SessionLocal() as db:
        try:
            # Get all active subscriptions
            result = await db.execute(
                select(UserSubscription)
                .where(UserSubscription.active == True)
                .where(
                    (UserSubscription.end_date == None) | 
                    (UserSubscription.end_date > datetime.utcnow())
                )
            )
            active_subs = result.scalars().all()
            
            reset_count = 0
            today = date.today()
            
            for sub in active_subs:
                # Get user
                user_result = await db.execute(
                    select(User).where(User.id == sub.user_id)
                )
                user = user_result.scalar_one_or_none()
                
                if not user:
                    continue
                
                # Check if already reset today
                if user.last_reset_date == today:
                    print(f"⏭️  Skipping {user.email} - already reset today")
                    continue
                
                old_credits = user.credits
                user.credits = sub.credits_per_day
                user.last_reset_date = today
                
                # Log in history
                db.add(CreditHistory(
                    user_id=user.id,
                    reason="Daily Reset",
                    credits_change=sub.credits_per_day - old_credits,
                    balance_after=user.credits,
                    instant_credits_change=0,
                    instant_balance_after=user.instant_credits,
                    created_at=datetime.utcnow()
                ))
                
                reset_count += 1
                print(f"✅ Reset {user.email}: {old_credits} → {user.credits} credits")
            
            await db.commit()
            print(f"\n✅ Successfully reset credits for {reset_count} users")
            print(f"{'='*60}\n")
            
        except Exception as e:
            print(f"❌ Error during credit reset: {str(e)}")
            await db.rollback()


if __name__ == "__main__":
    # For testing - run manually
    asyncio.run(reset_daily_credits())