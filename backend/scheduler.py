from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from database import SessionLocal
from credit_manager import process_all_users_credits

scheduler = AsyncIOScheduler()


async def daily_credit_job():
    """
    Job that runs daily to process all users' credits
    """
    print(f"🔄 Running daily credit renewal job at {datetime.now()}")
    
    async with AsyncSessionLocal() as db:
        try:
            await process_all_users_credits(db)
            print("✅ Daily credit job completed successfully")
        except Exception as e:
            print(f"❌ Error in daily credit job: {str(e)}")


def start_scheduler():
    """
    Start the background scheduler
    Runs daily at 00:01 (1 minute past midnight)
    """
    # Schedule job to run daily at 00:01
    scheduler.add_job(
        daily_credit_job,
        trigger=CronTrigger(hour=0, minute=1),
        id='daily_credit_renewal',
        replace_existing=True,
        misfire_grace_time=3600  # Allow 1 hour grace period if server was down
    )
    
    scheduler.start()
    print("📅 Credit renewal scheduler initialized")


def stop_scheduler():
    """
    Stop the background scheduler
    """
    scheduler.shutdown()
    print("🛑 Credit renewal scheduler stopped")