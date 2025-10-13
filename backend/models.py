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
    userid = Column(Integer, ForeignKey("users.id"), nullable=False)
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