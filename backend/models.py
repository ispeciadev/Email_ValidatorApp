from db import Base
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, ForeignKey
from datetime import datetime, timezone
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func


def utcnow():
    """Return timezone-aware UTC now"""
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")
    blocked = Column(Boolean, default=False)
    status = Column(String, default="pending")
    credits = Column(Integer, default=20)  # ✅ Simple credits field

    email_records = relationship("EmailRecord", back_populates="user")
    subscriptions = relationship("UserSubscription", back_populates="user")
    credit_orders = relationship("CreditOrder", back_populates="user")
    history = relationship("CreditHistory", back_populates="user")
    validation_tasks = relationship("ValidationTask", back_populates="user")

class EmailRecord(Base):
    __tablename__ = "email_records"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, nullable=False)
    regex = Column(String)
    mx = Column(String)
    smtp = Column(String)
    status = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="email_records")

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "regex": self.regex,
            "mx": self.mx,
            "smtp": self.smtp,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    stripe_plan_id = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    interval = Column(String, default="month")
    description = Column(String, nullable=True)


class UserSubscription(Base):
    __tablename__ = "user_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"))
    active = Column(Boolean, default=True)
    start_date = Column(DateTime, default=datetime.utcnow)
    end_date = Column(DateTime, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)

    user = relationship("User", back_populates="subscriptions")
    plan = relationship("SubscriptionPlan")


class CreditOrder(Base):
    __tablename__ = "credit_orders"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # ✅ Fixed field name
    credits = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    plan = Column(String, nullable=False)  # daily or instant
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="credit_orders")


class CreditHistory(Base):
    __tablename__ = "credit_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reason = Column(String)  # Purchase / Verification / Refund
    credits_change_daily = Column(Integer, default=0)
    credits_change_instant = Column(Integer, default=0)
    balance_after_daily = Column(Integer, default=0)
    balance_after_instant = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="history")


class ValidationTask(Base):
    __tablename__ = "validation_tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String, unique=True, index=True, nullable=False)  # batch_id
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String, nullable=False)
    status = Column(String, default="Completed")  # Pending, Processing, Completed, Failed
    total_emails = Column(Integer, default=0)
    progress = Column(Integer, default=100)  # 0-100
    
    # Category counts
    safe_count = Column(Integer, default=0)
    role_count = Column(Integer, default=0)
    catch_all_count = Column(Integer, default=0)
    disposable_count = Column(Integer, default=0)
    inbox_full_count = Column(Integer, default=0)
    spam_trap_count = Column(Integer, default=0)
    disabled_count = Column(Integer, default=0)
    invalid_count = Column(Integer, default=0)
    unknown_count = Column(Integer, default=0)
    
    download_url = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    user = relationship("User", back_populates="validation_tasks")
    
    def to_dict(self):
        return {
            "id": self.id,
            "task_id": self.task_id,
            "filename": self.filename,
            "status": self.status,
            "total_emails": self.total_emails,
            "progress": self.progress,
            "safe": self.safe_count,
            "role": self.role_count,
            "catch_all": self.catch_all_count,
            "disposable": self.disposable_count,
            "inbox_full": self.inbox_full_count,
            "spam_trap": self.spam_trap_count,
            "disabled": self.disabled_count,
            "invalid": self.invalid_count,
            "unknown": self.unknown_count,
            "download_url": self.download_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }