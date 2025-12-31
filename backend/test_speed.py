#!/usr/bin/env python3
"""
Speed test for the Fast Email Validator

Run this to verify you're getting 5-10+ emails per second.
Note: Emails from Gmail, Yahoo, Outlook etc. are marked "Risky" because
these providers block SMTP verification - we can't confirm mailbox exists.
"""

import asyncio
import time
import sys
sys.path.insert(0, '/home/Abhi/Downloads/Email_ValidatorApp-main/backend')

# Test emails - mix of valid, invalid, and different providers
TEST_EMAILS = [
    # Trusted providers (will be Risky - can't verify)
    "test@gmail.com",
    "user@yahoo.com",
    "john.doe@outlook.com",
    "alice@hotmail.com",
    "bob@icloud.com",
    "test123@protonmail.com",
    "user@aol.com",
    "hello@ymail.com",
    "contact@fastmail.com",
    "info@zoho.com",
    
    # Invalid emails (syntax - instant)
    "invalid",
    "no@tld",
    "@nodomain.com",
    "spaces in@email.com",
    "double..dot@test.com",
    
    # Disposable domains (instant)
    "temp@mailinator.com",
    "fake@guerrillamail.com",
    
    # Real domains requiring SMTP check
    "test@github.com",
    "support@amazon.com",
    "info@microsoft.com",
]


async def run_speed_test():
    """Run speed test"""
    from validator.fast_validator import get_fast_validator, validate_bulk_fast
    
    print("=" * 60)
    print("FAST EMAIL VALIDATOR SPEED TEST")
    print("=" * 60)
    
    # Initialize validator
    print("\n[1] Initializing validator...")
    validator = await get_fast_validator()
    print("    ✓ Validator ready")
    
    # Test single email validation
    print("\n[2] Testing single email validation...")
    start = time.time()
    result = await validator.validate_email("test@gmail.com")
    single_time = time.time() - start
    print(f"    ✓ Single email: {single_time*1000:.0f}ms")
    print(f"    Status: {result['status']}, Reason: {result['reason']}")
    
    # Test bulk validation
    print(f"\n[3] Testing bulk validation ({len(TEST_EMAILS)} emails)...")
    start = time.time()
    results = await validate_bulk_fast(TEST_EMAILS)
    bulk_time = time.time() - start
    
    valid_count = sum(1 for r in results if r['status'] == 'Valid')
    risky_count = sum(1 for r in results if r['status'] == 'Risky')
    invalid_count = len(results) - valid_count - risky_count
    rate = len(TEST_EMAILS) / max(bulk_time, 0.001)
    
    print(f"    ✓ Bulk validation complete")
    print(f"    Time: {bulk_time:.2f}s")
    print(f"    Rate: {rate:.1f} emails/second")
    print(f"    Valid: {valid_count}, Risky: {risky_count}, Invalid: {invalid_count}")
    
    # Show cache stats
    print(f"\n[4] Cache stats:")
    stats = validator.get_cache_stats()
    for key, value in stats.items():
        print(f"    {key}: {value}")
    
    # Detailed results
    print("\n[5] Detailed results:")
    print("-" * 60)
    for r in results:
        status_icon = "✓" if r['status'] == 'Valid' else "✗"
        print(f"    {status_icon} {r['email'][:30]:<30} | {r['status']:<10} | {r['reason'][:25]}")
    
    # Speed assessment
    print("\n" + "=" * 60)
    if rate >= 10:
        print(f"🚀 EXCELLENT! {rate:.1f} emails/sec (target: 10+)")
    elif rate >= 5:
        print(f"✓ GOOD! {rate:.1f} emails/sec (target: 5-10)")
    else:
        print(f"⚠ NEEDS OPTIMIZATION: {rate:.1f} emails/sec (target: 5+)")
    print("=" * 60)


async def run_stress_test(n_emails: int = 100):
    """Run stress test with many emails"""
    from validator.fast_validator import validate_bulk_fast
    
    print(f"\n[STRESS TEST] Validating {n_emails} emails...")
    
    # Generate test emails
    domains = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "test.com", "example.org"]
    emails = [f"user{i}@{domains[i % len(domains)]}" for i in range(n_emails)]
    
    start = time.time()
    results = await validate_bulk_fast(emails)
    elapsed = time.time() - start
    
    rate = n_emails / max(elapsed, 0.001)
    print(f"✓ Completed: {n_emails} emails in {elapsed:.2f}s ({rate:.1f} emails/sec)")
    
    return rate


if __name__ == "__main__":
    print("\n🔥 Starting Fast Email Validator Speed Test...\n")
    
    # Run main test
    asyncio.run(run_speed_test())
    
    # Optional: Run stress test
    print("\n" + "=" * 60)
    print("Running additional stress tests...")
    asyncio.run(run_stress_test(50))
    asyncio.run(run_stress_test(100))
