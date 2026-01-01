"""
Test script for async email validation engine
Tests the production-grade async validator before full integration
"""
import asyncio
import sys
import time
from pathlib import Path

# Add validator to path
sys.path.insert(0, str(Path(__file__).parent))

from validator.async_validator import validate_email_async, validate_bulk_async

async def test_single_validations():
    """Test individual email validation"""
    print("\n" + "="*70)
    print(" PHASE 1: Single Email Validation Tests")
    print("="*70)
    
    test_emails = [
        ("invalid@", "Invalid syntax"),
        ("test@guerrillamail.com", "Disposable"),
        ("user@nonexistentdomain12345.com", "No domain/MX"),
        ("test@gmail.com", "Free provider (Gmail)"),
        ("admin@gmail.com", "Role-based"),
    ]
   
    for email, description in test_emails:
        print(f"\n[TEST] {description}: {email}")
        start = time.time()
        result = await validate_email_async(email)
        elapsed = (time.time() - start) * 1000
        
        print(f"  Status: {result['status']}")
        print(f"  Sub-status: {result['sub_status']}")
        print(f"  Score: {result['score']}/100")
        print(f"  Time: {elapsed:.1f}ms")

async def test_bulk_validation():
    """Test bulk validation performance"""
    print("\n" + "="*70)
    print(" PHASE 2: Bulk Validation Performance Test")
    print("="*70)
    
    # Create test dataset
    bulk_emails = []
    
    # 100 invalid syntax
    bulk_emails.extend([f"invalid{i}@" for i in range(100)])
    
    # 100 disposable
    bulk_emails.extend([f"test{i}@guerrillamail.com" for i in range(100)])
    
    # 200 free providers
    bulk_emails.extend([f"user{i}@gmail.com" for i in range(100)])
    bulk_emails.extend([f"person{i}@yahoo.com" for i in range(100)])
    
    print(f"\nTesting with {len(bulk_emails)} emails...")
    print(f"Expected time: ~{len(bulk_emails)/67:.1f}s (67 emails/sec target)")
    
    start_time = time.time()
    results = await validate_bulk_async(bulk_emails)
    elapsed = time.time() - start_time
    
    # Count by status
    status_counts = {}
    for r in results:
        status = r.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    
    print(f"\nRESULTS:")
    print(f"  Total: {len(results)}")
    print(f"  Time: {elapsed:.2f}s")
    print(f"  Speed: {len(results)/elapsed:.1f} emails/sec")
    print(f"\nStatus breakdown:")
    for status, count in sorted(status_counts.items()):
        pct = (count / len(results)) * 100
        print(f"  {status.upper()}: {count} ({pct:.1f}%)")
    
    # Performance check
    target_time = 30.0  # 30 seconds for 2000 emails
    projected_2000 = (2000 / len(results)) * elapsed
    print(f"\n📊 PROJECTED TIME FOR 2000 EMAILS: {projected_2000:.1f}s")
    
    if projected_2000 < target_time:
        print(f"✅ PASS - Under 30 second target!")
    else:
        print(f"⚠️  NEEDS OPTIMIZATION - {projected_2000 - target_time:.1f}s over target")

async def main():
    """Run all tests"""
    print("\n" + "="*70)
    print(" ASYNC EMAIL VALIDATOR - PRODUCTION TEST")
    print("="*70)
    
    try:
        # Test 1: Single validations
        await test_single_validations()
        
        # Test 2: Bulk validation
        await test_bulk_validation()
        
        print("\n" + "="*70)
        print(" ALL TESTS COMPLETE")
        print("="*70 + "\n")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Run async tests
    asyncio.run(main())
