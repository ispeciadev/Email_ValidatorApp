from fastapi import FastAPI, UploadFile, File, Form, APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import csv, os, time
from typing import List, Dict, Optional, Literal, Any
from sqlalchemy.ext.asyncio import AsyncSession
from db import engine
from sqlalchemy.future import select
from models import EmailRecord, Base, User, CreditHistory, ValidationTask
from db import get_db
from config import DATABASE_URL

# Validator mode: "async" (production), "fast" (default), or "strict"
VALIDATOR_MODE = os.getenv("VALIDATOR_MODE", "async").lower()

if VALIDATOR_MODE == "async":
    # NEW: Production-grade async validator (2,200 emails in <30s)
    print("INFO: Using ASYNC PRODUCTION validator (domain-pooled SMTP, <30s for 2000 emails)")
    from validator.async_validator import validate_email_async, validate_bulk_async
    
    # Wrapper to match existing interface
    async def process_emails_async_wrapper(emails, batch_id=None, validation_type="individual"):
        if len(emails) == 1:
            result = await validate_email_async(emails[0])
            if batch_id:
                result["batch_id"] = batch_id
            return [result], 1, 1 if result["status"] == "VALID" else 0, 0 if result["status"] == "VALID" else 1, []
        else:
            results = await validate_bulk_async(emails, batch_id)
            total = len(results)
            valid = sum(1 for r in results if r.get("status") == "VALID")
            invalid = total - valid
            failed = [r["email"] for r in results if r.get("status") != "VALID"]
            return results, total, valid, invalid, failed
    
    # Use the wrapper
    process_emails_async = process_emails_async_wrapper
    
elif VALIDATOR_MODE == "strict":
    # Import STRICT validator (4-stage gated pipeline)
    from validator.strict_validator import (
        StrictEmailValidator as AsyncEmailValidator,
        get_strict_validator as get_validator,
        validate_email_strict as validate_email_async,
        validate_bulk_strict as validate_bulk_async,
        validate_syntax as check_syntax_func,
    )
    from validator.fast_validator import (
        check_disposable_fast as check_disposable,
        check_blacklist_fast as check_blacklist,
        check_role_fast as is_role_based
    )
    def check_syntax_fast(email):
        status, reason, local, domain = check_syntax_func(email)
        return status == "valid", reason, local, domain
    print("INFO: Using STRICT validator (4-stage gated pipeline)")
else:
    # Import FAST validator (10+ emails/sec)
    from validator.fast_validator import (
        FastEmailValidator as AsyncEmailValidator, 
        get_fast_validator as get_validator, 
        validate_email_fast as validate_email_async, 
        validate_bulk_fast as validate_bulk_async,
        check_syntax_fast,
        check_disposable_fast as check_disposable,
        check_blacklist_fast as check_blacklist,
        check_role_fast as is_role_based
    )
    print("INFO: Using FAST validator (optimized for speed)")

from contextlib import asynccontextmanager
from uuid import uuid4
from sqlalchemy import func, case
import bcrypt
from signup import router as signup_router
from jose import jwt
from datetime import datetime, timedelta
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

print("DEBUG: Using DATABASE_URL:", DATABASE_URL)

router = APIRouter()

# Global async validator instance (not used in async mode, but needed for compatibility)
_async_validator: Optional[Any] = None

# Placeholder for async mode (not needed since we import functions directly)
if VALIDATOR_MODE == "async":
    AsyncEmailValidator = None
    get_validator = None
else:
    # Already defined by the imports above
    pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _async_validator
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("SUCCESS: Tables synced with database.")
        
        # Initialize async validator with warm-up (only for non-async modes)
        if VALIDATOR_MODE != "async":
            _async_validator = AsyncEmailValidator()
            await _async_validator.initialize()
            print("SUCCESS: Async email validator initialized with warm-up.")
        else:
            print("SUCCESS: Async production validator loaded (no initialization needed).")
    except Exception as e:
        print(f"ERROR during startup: {e}")
    yield
    # Cleanup on shutdown
    if _async_validator:
        await _async_validator.cleanup()
    print("Shutting down app.")

app = FastAPI(lifespan=lifespan)

# Allowed origins for CORS - support both local and production
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "https://email-validator-frontend.onrender.com",
    "https://email-validatorapp.onrender.com",
    "https://email-validatorapp-frontend.onrender.com",
]

# Add FRONTEND_URL from env if set
FRONTEND_URL = os.getenv("FRONTEND_URL")
if FRONTEND_URL and FRONTEND_URL not in ALLOWED_ORIGINS:
    ALLOWED_ORIGINS.append(FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Constants
BATCH_SIZE = 250  # Optimized batch size for async processing

@app.get("/")
def read_root():
    return {"message": "Email Validator Backend is running (High-Performance Async Mode)"}

# ======================= Email Validation Core =======================

async def process_emails_async(emails: List[str], batch_id: str = None, validation_type: str = "individual"):
    """
    High-performance async email validation.
    Uses the appropriate validator based on VALIDATOR_MODE.
    """
    global _async_validator
    
    # Check if we're using the new async production validator
    if VALIDATOR_MODE == "async":
        # Use new async validator directly (already imported)
        start_time = time.time()
        
        if len(emails) == 1:
            result = await validate_email_async(emails[0])
            if batch_id:
                result["batch_id"] = batch_id
            results = [result]
        else:
            results = await validate_bulk_async(emails, batch_id)
        
        elapsed = time.time() - start_time
        print(f"PERF: Validated {len(emails)} emails in {elapsed:.2f}s ({len(emails)/max(elapsed, 0.001):.1f} emails/sec)")
        
        total = len(results)
        # Safe (Valid) and Role (Valid) are considered 'valid' for general counts
        valid_statuses = ("valid", "role")
        valid = sum(1 for r in results if r.get("status") in valid_statuses)
        invalid = sum(1 for r in results if r.get("status") == "invalid")
        # Everything else (unknown, catch_all, etc.) is in the middle but counted as 'invalid' for the simple valid/invalid split
        failed_emails = [r.get("email") for r in results if r.get("status") not in ("valid", "role")]
        
        return results, total, valid, invalid, failed_emails
    
    # Existing validator logic fallback (should rarely hit with os.env async mode)
    if _async_validator is None:
        _async_validator = await get_validator()
    
    start_time = time.time()
    if validation_type == "bulk" or len(emails) > 1:
        results = await _async_validator.validate_bulk(emails, batch_id)
    else:
        result = await _async_validator.validate_email(emails[0])
        results = [result]
    
    total = len(emails)
    valid = sum(1 for r in results if str(r.get("status")).lower() in ("valid", "safe", "role"))
    invalid = total - valid
    failed_emails = [r.get("email") for r in results if str(r.get("status")).lower() not in ("valid", "safe", "role")]
    
    return results, total, valid, invalid, failed_emails

# ======================= Models =======================

class LoginData(BaseModel):
    email: str
    password: str

class BlockData(BaseModel):
    id: int
    blocked: bool

class AddCreditsRequest(BaseModel):
    user_id: int
    credits: int = Field(..., gt=0)

class UserUpdate(BaseModel):
    id: int
    email: str
    role: str
    status: str

class BuyCreditsRequest(BaseModel):
    credits: int = Field(..., gt=0)
    price: float = Field(..., gt=0)
    user_id: int
    plan: Literal["instant", "monthly"] = "instant"
    package_name: Optional[str] = None

class SubscriptionRequest(BaseModel):
    credits_per_day: int = Field(..., gt=0)
    monthly_cost: float = Field(..., gt=0)
    discount: int = Field(default=0, ge=0, le=100)

class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None


# ======================= Auth =======================

def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

SECRET_KEY = "aisha-negi"
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def create_token(user_id: int):
    payload = {"sub": str(user_id), "exp": datetime.utcnow() + timedelta(hours=24)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = int(payload.get("sub"))
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Token decode error")

# ======================= User Routes =======================

@app.post("/login")
async def login(data: LoginData, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not bcrypt.checkpw(data.password.encode(), user.hashed_password.encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="Account is not activated.")
    if user.blocked:
        raise HTTPException(status_code=403, detail="Account is blocked.")
    token = create_token(user.id)
    return {
        "message": "Login successful",
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "token": token,
        "credits": user.credits
    }

@app.get("/user/credits")
async def get_user_credits(current_user: User = Depends(get_current_user)):
    return {"credits": current_user.credits, "email": current_user.email, "name": current_user.name}

@app.get("/user/records")
async def get_user_records(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EmailRecord).where(EmailRecord.user_id == current_user.id))
    records = result.scalars().all()
    return [record.to_dict() for record in records]

@app.put("/user/profile")
async def update_user_profile(
    data: UserProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update user profile information (name, email, password)"""
    try:
        # If changing password, verify current password first
        if data.new_password:
            if not data.current_password:
                raise HTTPException(status_code=400, detail="Current password is required to change password")
            
            if not bcrypt.checkpw(data.current_password.encode(), current_user.hashed_password.encode()):
                raise HTTPException(status_code=401, detail="Current password is incorrect")
            
            # Hash the new password
            hashed_new_password = bcrypt.hashpw(data.new_password.encode(), bcrypt.gensalt()).decode()
            current_user.hashed_password = hashed_new_password
        
        # Update name if provided
        if data.name:
            current_user.name = data.name
        
        # Update email if provided and check uniqueness
        if data.email and data.email != current_user.email:
            # Check if email already exists
            result = await db.execute(select(User).where(User.email == data.email))
            existing_user = result.scalar_one_or_none()
            if existing_user:
                raise HTTPException(status_code=400, detail="Email already in use")
            current_user.email = data.email
        
        await db.commit()
        await db.refresh(current_user)
        
        return {
            "message": "Profile updated successfully",
            "user": {
                "id": current_user.id,
                "name": current_user.name,
                "email": current_user.email,
                "role": current_user.role,
                "credits": current_user.credits
            }
        }
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating profile: {str(e)}")


# ======================= Email Validation =======================

@app.post("/validate-emails/")
async def validate_emails(
    files: List[UploadFile] = File([]),
    email: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    print(f"BULK validation requested by {current_user.email}")
    start_time = time.time()
    response_payload = []
    batch_id = uuid4().hex
    try:
        if email:
            # Re-direct to single validation logic if email is provided here
            return await validate_single_email(email=email, db=db, current_user=current_user)

        if files:
            for file in files:
                contents = await file.read()
                lines = contents.decode(errors='ignore').splitlines()
                try:
                    reader = csv.DictReader(lines)
                    emails = [row.get('email', '').strip() for row in reader if row.get('email')]
                    if not emails:
                         emails = [line.strip() for line in lines if line.strip()]
                except Exception:
                    emails = [line.strip() for line in lines if line.strip()]

                # REQ 15: Automatically remove duplicate emails
                emails = list(dict.fromkeys([e.lower() for e in emails if e]))
                
                if not emails:
                    continue

                if current_user.credits < len(emails):
                    raise HTTPException(
                        status_code=403, 
                        detail=f"Insufficient credits. You need {len(emails)} credits for this file, but only have {current_user.credits}."
                    )

                # REQ 22: Cache / Deduplicate against DB if needed (Optional but suggested)
                # For now, we process all provided unique emails.

                results, total, valid, invalid, _ = await process_emails_async(emails, batch_id=batch_id, validation_type="bulk")
                
                # REQ: Deduct only for non-error results (anything that gives a status)
                successful_results = [r for r in results if r.get("status") not in ["unknown", "error"]]
                deduction_count = len(successful_results)
                
                if deduction_count > 0:
                    current_user.credits -= deduction_count
                    db.add(CreditHistory(
                        user_id=current_user.id,
                        reason=f"Bulk Verification - {file.filename}",
                        credits_change_instant=-deduction_count,
                        balance_after_instant=current_user.credits
                    ))
                else:
                    print(f"DEBUG: No credits deducted for {file.filename} as all validations failed.")

                for result in results:
                    db.add(EmailRecord(
                        email=result["email"], 
                        regex=result.get("regex", "N/A"), 
                        mx=result.get("mx", "N/A"),
                        smtp=result.get("smtp", "N/A"), 
                        status=result["status"],
                        created_at=datetime.utcnow(), 
                        user_id=current_user.id
                    ))
                
                # Calculate detailed category counts for visualization (Status-driven)
                safe_count = role_count = catch_all_count = disposable_count = 0
                inbox_full_count = spam_trap_count = disabled_count = invalid_count = unknown_count = 0
                
                # Status-driven aggregation (Principal Architect Rule)
                for r in results:
                    status = r.get("status", "unknown")
                    if status == "valid": safe_count += 1
                    elif status == "role": role_count += 1
                    elif status == "catch_all": catch_all_count += 1
                    elif status == "disposable": disposable_count += 1
                    elif status == "inbox_full": inbox_full_count += 1
                    elif status == "spamtrap": spam_trap_count += 1
                    elif status == "disabled": disabled_count += 1
                    elif status == "invalid": invalid_count += 1
                    else: unknown_count += 1

                
                
                validated_filename = f"validated_{batch_id}_{file.filename}"
                # Save results to a file for download (Architect Format)
                with open(validated_filename, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=[
                        'email', 'status', 'sub_status', 'score', 
                        'syntax_val', 'domain_exists', 'mx_record', 
                        'is_disposable', 'is_role', 'is_catch_all', 'verdict'
                    ])
                    writer.writeheader()
                    writer.writerows([
                        {
                            "email": r["email"], 
                            "status": r.get("status"),
                            "sub_status": r.get("sub_status"),
                            "score": r.get("score"),
                            "syntax_val": r.get("checks", {}).get("syntax"),
                            "domain_exists": r.get("checks", {}).get("domain"),
                            "mx_record": r.get("checks", {}).get("mx"),
                            "is_disposable": r.get("is_disposable"),
                            "is_role": r.get("is_role_account"),
                            "is_catch_all": r.get("is_catch_all"),
                            "verdict": r.get("status")
                        } for r in results
                    ])

                response_payload.append({
                    "file": file.filename, "total": total, "valid": valid, "invalid": invalid,
                    "safe": safe_count,
                    "role": role_count,
                    "catch_all": catch_all_count,
                    "disposable": disposable_count,
                    "inbox_full": inbox_full_count,
                    "spam_trap": spam_trap_count,
                    "disabled": disabled_count,
                    "invalid": invalid_count,
                    "unknown": unknown_count,
                    "validated_download": f"/download/{validated_filename}",
                    "credits_remaining": current_user.credits,
                    "batch_id": batch_id
                })
                
                # Save validation task to database for history
                validation_task = ValidationTask(
                    task_id=batch_id,
                    user_id=current_user.id,
                    filename=file.filename,
                    status="Completed",
                    total_emails=total,
                    progress=100,
                    safe_count=safe_count,
                    role_count=role_count,
                    catch_all_count=catch_all_count,
                    disposable_count=disposable_count,
                    inbox_full_count=inbox_full_count,
                    spam_trap_count=spam_trap_count,
                    disabled_count=disabled_count,
                    invalid_count=invalid_count,
                    unknown_count=unknown_count,
                    download_url=f"/download/{validated_filename}",
                    completed_at=datetime.utcnow()
                )
                db.add(validation_task)
            
            await db.commit()
            return {"message": "Validation completed", "results": response_payload}

        return {"message": "No data provided", "results": []}
    except HTTPException as http_exc:
        # Re-raise HTTP exceptions as-is
        raise http_exc
    except Exception as e:
        await db.rollback()
        import traceback
        error_details = traceback.format_exc()
        print(f"ERROR: BULK VALIDATION ERROR: {e}")
        print(f"ERROR TRACEBACK:\n{error_details}")
        raise HTTPException(status_code=500, detail=f"Validation error: {str(e)}")

@app.post("/validate-single-email/")
async def validate_single_email(
    email: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Validate a single email with credit deduction and history logging"""
    print(f"DEBUG: Single validation for {email} by {current_user.email}")
    start_time = time.time()
    email = email.strip().lower()
    
    try:
        if current_user.credits < 1:
            raise HTTPException(status_code=403, detail="Insufficient credits. Please top up your account.")
        
        # REQ 22: Cache check - BYPASSED AS PER USER REQUEST (Always real-time)
        # result = await db.execute(select(EmailRecord).where(EmailRecord.email == email).order_by(EmailRecord.created_at.desc()))
        # cached_record = result.scalars().first()
        
        # if cached_record and (datetime.utcnow() - cached_record.created_at).total_seconds() < 86400:
        #     print(f"DEBUG: Using cached result for {email}")
        #     # Ensure we return standardized strings even from cache
        #     return {
        #         "email": cached_record.email,
        #         "is_valid": cached_record.status == "Valid",
        #         "status": cached_record.status,
        #         "regex": cached_record.regex if cached_record.regex else "Valid",
        #         "mx": cached_record.mx if cached_record.mx else "Valid",
        #         "smtp": cached_record.smtp if cached_record.smtp else "Valid",
        #         "disposable": "No", # Cache doesn't store these yet, providing safe defaults
        #         "role_based": "No",
        #         "score": 0,
        #         "grade": "N/A",
        #         "credits_remaining": current_user.credits,
        #         "cached": True
        #     }

        # No cache, call VerifyKit
        results, total, valid, invalid, _ = await process_emails_async([email], validation_type="individual")
        
        # Deduct credit only if successful
        if results[0].get("status") not in ["Error", "Unknown"]:
            current_user.credits -= 1
            # Log to history
            db.add(CreditHistory(
                user_id=current_user.id,
                reason=f"Single Email Verification - {email}",
                credits_change_instant=-1,
                balance_after_instant=current_user.credits
            ))
        else:
            print(f"DEBUG: No credit deducted for {email} due to validation error.")
        
        # Save email record
        for result in results:
            db.add(EmailRecord(
                email=result["email"], 
                regex=result.get("regex"),
                mx=result.get("mx"),
                smtp=result.get("smtp"),
                status=result["status"],
                created_at=datetime.utcnow(), 
                user_id=current_user.id
            ))
        
        await db.commit()
        print(f"SUCCESS: Validation successful for {email}")
        
        resp = {
            "email": results[0]["email"],
            "is_valid": results[0]["status"] in ("valid", "role"),
            "status": results[0]["status"],
            "reason": results[0].get("reason", "N/A"),
            "syntax_valid": results[0].get("checks", {}).get("syntax", False),
            "mx_valid": results[0].get("checks", {}).get("mx", False),
            "smtp_status": results[0].get("checks", {}).get("smtp", "N/A"),
            "disposable": results[0].get("is_disposable", False),
            "role_based": results[0].get("is_role_account", False),
            "catch_all": results[0].get("is_catch_all", False),
            "score": results[0].get("score", 0),
            "grade": results[0].get("quality_grade", "N/A"),
            "time_taken": round(time.time() - start_time, 2),
            "credits_remaining": current_user.credits,
            # Keys expected by frontend components
            "regex": "Valid" if results[0].get("checks", {}).get("syntax") else "Not Valid",
            "mx": "Valid" if results[0].get("checks", {}).get("mx") else "Not Valid",
            "smtp": "Valid" if results[0]["status"] in ("valid", "role") else "Not Valid"
        }
        print(f"DEBUG: Final Response to Frontend: {resp}")
        return resp
    except Exception as e:
        await db.rollback()
        import traceback
        traceback.print_exc()
        print(f"ERROR: VALIDATION ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/{filename}")
def download_file(filename: str):
    file_path = os.path.join(".", filename)
    if os.path.exists(file_path):
        return FileResponse(path=file_path, media_type='text/csv', filename=filename)
    raise HTTPException(status_code=404, detail="File not found")

@app.get("/download-valid/{filename}")
def download_valid_emails(filename: str):
    """Download CSV file containing only valid emails (Safe and Role-based)"""
    file_path = os.path.join(".", filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    # Create filtered CSV with only valid emails
    valid_filename = filename.replace("validated_", "valid_only_")
    valid_file_path = os.path.join(".", valid_filename)
    
    try:
        with open(file_path, 'r', newline='', encoding='utf-8') as infile:
            reader = csv.DictReader(infile)
            fieldnames = reader.fieldnames
            
            # Filter for valid emails (Architect Style: valid, role)
            valid_rows = [row for row in reader if row.get('status') in ('valid', 'role')]
            
            # Write filtered data to new file
            with open(valid_file_path, 'w', newline='', encoding='utf-8') as outfile:
                writer = csv.DictWriter(outfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(valid_rows)
        
        return FileResponse(path=valid_file_path, media_type='text/csv', filename=valid_filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating filtered file: {str(e)}")

@app.get("/download-invalid/{filename}")
def download_invalid_emails(filename: str):
    """Download CSV file containing only invalid emails (Invalid, Disposable, Disabled, etc.)"""
    file_path = os.path.join(".", filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    # Create filtered CSV with only invalid emails
    invalid_filename = filename.replace("validated_", "invalid_only_")
    invalid_file_path = os.path.join(".", invalid_filename)
    
    try:
        with open(file_path, 'r', newline='', encoding='utf-8') as infile:
            reader = csv.DictReader(infile)
            fieldnames = reader.fieldnames
            
            # Filter for invalid emails (anything not valid or role)
            invalid_rows = [row for row in reader if row.get('status') not in ('valid', 'role')]
            
            # Write filtered data to new file
            with open(invalid_file_path, 'w', newline='', encoding='utf-8') as outfile:
                writer = csv.DictWriter(outfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(invalid_rows)
        
        return FileResponse(path=invalid_file_path, media_type='text/csv', filename=invalid_filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating filtered file: {str(e)}")

# ======================= Credits =======================

@app.post("/api/credits/buy")
async def buy_credits(data: BuyCreditsRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        order_id = f"ORD-{uuid4().hex[:8].upper()}"
        old_balance = current_user.credits
        current_user.credits += data.credits
        
        # Log to history
        db.add(CreditHistory(
            user_id=current_user.id,
            reason=f"Purchase - {data.package_name or f'{data.credits} credits'}",
            credits_change_instant=data.credits,
            balance_after_instant=current_user.credits
        ))
        
        await db.commit()
        await db.refresh(current_user)
        
        return {
            "success": True, "order_id": order_id,
            "credits_purchased": data.credits, "new_balance": current_user.credits
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/credits/subscribe")
async def subscribe_monthly(data: SubscriptionRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        monthly_credits = data.credits_per_day * 30
        current_user.credits += monthly_credits
        
        # Log to history
        db.add(CreditHistory(
            user_id=current_user.id,
            reason="Monthly Subscription",
            credits_change_instant=monthly_credits,
            balance_after_instant=current_user.credits
        ))
        
        await db.commit()
        return {"success": True, "monthly_credits": monthly_credits, "new_balance": current_user.credits}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/credits/balance")
async def get_credit_balance(current_user: User = Depends(get_current_user)):
    return {"success": True, "credits": current_user.credits}

@app.get("/api/credits/my-history")
async def get_my_credit_history(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(CreditHistory).where(CreditHistory.user_id == current_user.id)
        .order_by(CreditHistory.created_at.desc()).limit(100)
    )
    history = result.scalars().all()
    
    # Debug logging
    print(f"INFO: Fetching history for user {current_user.email}")
    print(f"Found {len(history)} records")
    
    response = []
    for r in history:
        record = {
            "id": r.id,
            "reason": r.reason or "Unknown",
            "credits_change_instant": r.credits_change_instant or 0,
            "balance_after_instant": r.balance_after_instant or 0,
            "created_at": r.created_at.isoformat() if r.created_at else None
        }
        response.append(record)
        print(f"  - {r.reason}: {r.credits_change_instant} credits, balance: {r.balance_after_instant}")
    
    return response

# ======================= Admin =======================

@app.post("/api/add-credits")
async def admin_add_credits(data: AddCreditsRequest, db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(User).where(User.id == data.user_id))
        target_user = result.scalar_one_or_none()
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")
        
        old_balance = target_user.credits
        target_user.credits += data.credits
        
        # Log to history
        db.add(CreditHistory(
            user_id=target_user.id,
            reason="Admin Credit Addition",
            credits_change_instant=data.credits,
            balance_after_instant=target_user.credits
        ))
        
        await db.commit()
        await db.refresh(target_user)
        
        return {
            "success": True, "message": f"Added {data.credits} credits",
            "new_balance": target_user.credits
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users")
async def get_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User))
    return result.scalars().all()

@router.post("/block-user")
async def block_user(data: BlockData, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == data.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.blocked = data.blocked
    await db.commit()
    return {"message": "User updated"}

@router.delete("/delete-user/{user_id}")
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)
    await db.commit()
    return {"message": "User deleted"}

@router.put("/update-user")
async def update_user(data: UserUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == data.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.email = data.email
    user.role = data.role
    user.status = data.status
    await db.commit()
    return {"message": "User updated"}

# ======================= Stats =======================

@app.get("/summary")
async def get_summary(db: AsyncSession = Depends(get_db)):
    total = await db.scalar(select(func.count()).select_from(EmailRecord))
    valid = await db.scalar(select(func.count()).select_from(EmailRecord).where(EmailRecord.status == "Valid"))
    return {"total_uploads": total, "valid_emails": valid, "invalid_emails": total - valid}

@app.get("/admin/email-stats")
async def get_email_stats(db: AsyncSession = Depends(get_db)):
    total = await db.scalar(select(func.count()).select_from(EmailRecord))
    valid = await db.scalar(select(func.count()).select_from(EmailRecord).where(EmailRecord.status == "Valid"))
    return {"counts": {"total": total, "valid": valid, "invalid": total - valid}}

@app.get("/user/all-emails")
async def get_all_emails_for_user(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(EmailRecord).where(EmailRecord.user_id == current_user.id))
    records = result.scalars().all()
    return [r.to_dict() for r in records]

@app.get("/user/validation-tasks")
async def get_user_validation_tasks(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get all validation tasks for the current user"""
    result = await db.execute(
        select(ValidationTask)
        .where(ValidationTask.user_id == current_user.id)
        .order_by(ValidationTask.created_at.desc())
    )
    tasks = result.scalars().all()
    return [task.to_dict() for task in tasks]

@app.get("/user/validation-task/{task_id}")
async def get_validation_task_details(task_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get detailed information about a specific validation task"""
    result = await db.execute(
        select(ValidationTask)
        .where(ValidationTask.task_id == task_id, ValidationTask.user_id == current_user.id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Validation task not found")
    
    return task.to_dict()

@app.delete("/user/validation-task/{task_id}")
async def delete_validation_task(task_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Delete a validation task"""
    result = await db.execute(
        select(ValidationTask)
        .where(ValidationTask.task_id == task_id, ValidationTask.user_id == current_user.id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Validation task not found")
    
    await db.delete(task)
    await db.commit()
    
    return {"message": "Validation task deleted successfully", "task_id": task_id}

@app.get("/api/validation-stats/weekly")
async def get_weekly_stats(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    today = datetime.utcnow()
    week_ago = today - timedelta(days=7)
    
    # PostgreSQL uses EXTRACT(DOW FROM ...) for day of week (0=Sunday, 6=Saturday)
    # We'll map these to Mon-Sun
    result = await db.execute(
        select(
            func.extract('dow', EmailRecord.created_at).label("day_num"),
            func.count().label("emails")
        ).where(
            EmailRecord.user_id == user.id,
            EmailRecord.created_at >= week_ago
        ).group_by("day_num")
    )
    rows = result.fetchall()
    day_map = {0: "Sun", 1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat"}
    data = [{"day": day_map.get(int(row[0]), "Unknown"), "emails": row[1]} for row in rows]
    return data



@app.get("/admin/recent-results")
async def get_recent_results(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EmailRecord).order_by(EmailRecord.created_at.desc()).limit(100)
    )
    records = result.scalars().all()
    return [r.to_dict() for r in records]

# ======================= Performance Metrics =======================

@app.get("/api/metrics")
async def get_validation_metrics():
    """Get performance metrics for email validation (DNS times, SMTP times, etc.)"""
    global _async_validator
    if _async_validator is None:
        return {"error": "Validator not initialized", "metrics": {}}
    
    metrics = _async_validator.get_metrics()
    pool_stats = _async_validator._connection_pool.stats()
    cache_size = _async_validator._mx_cache.size()
    
    return {
        "status": "ok",
        "mx_cache_size": cache_size,
        "connection_pools": pool_stats,
        "domain_metrics": metrics,
        "config": {
            "max_concurrent_validations": 400,
            "dns_timeout_sec": 1.5,
            "smtp_timeout_sec": 2.0,
            "chunk_size": 250,
        }
    }

# ======================= Include Routers =======================

app.include_router(router, prefix="/admin")
app.include_router(signup_router)