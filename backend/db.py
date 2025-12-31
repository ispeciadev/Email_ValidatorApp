import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

# Load environment variables from .env
load_dotenv()

# Load the DATABASE_URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set in .env file or environment variables.")

# Convert postgresql:// to postgresql+asyncpg:// for async driver
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Create the SQLAlchemy base
Base = declarative_base()

# Create async engine for PostgreSQL (async engines handle pooling automatically)
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Disable echo to reduce overhead
    future=True,
    pool_size=5,  # Reduced for Render free tier (was 20)
    max_overflow=5,  # Reduced for Render free tier (was 10)
    pool_pre_ping=True,  # Verify connections before using them
    pool_recycle=3600  # Recycle connections after 1 hour
)

# Create async session factory
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Dependency to use in FastAPI routes
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
        
# Initialize all models (create tables)
async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=AsyncSession
)