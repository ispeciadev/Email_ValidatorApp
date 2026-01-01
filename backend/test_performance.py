"""
Quick Performance Test for Email Validator
Tests the optimized fail-fast validation system
Target: 2000 emails in < 30 seconds
"""
import time
from validator.multi_layer_check import multi_layer_validate, bulk_validate_local

# Test cases covering different scenarios
test_emails = [
    # Invalid syntax (should fail instantly ~1ms)
    "invalid@",
    "no-at-sign.com",
    "@nodomain.com",
    
    # Disposable emails (should fail instantly ~1ms)
    "test@guerrillamail.com",
    "temp@tempmail.com", 
    "fake@10minutemail.com",
    
    # No domain/MX (should fail in ~100-200ms)
    "user@nonexistentdomain12345.com",
    "test@invaliddomain999.net",
    
    # Free providers (should skip SMTP, ~100ms)
    "test@gmail.com",
    "user@yahoo.com",
    "person@outlook.com",
    "contact@hotmail.com",
    
    # Valid custom domain (may check SMTP, ~1-2s if not free)
    "info@example.com",
]

print("="*80)
print("PERFORMANCE TEST - Email Validator Optimization")
print("="*80)

# Test 1: Individual email validation
print("\n\n[TEST 1] Individual Email Validation Speed")
print("-" * 80)

for email in test_emails[:5]:  # Test first 5
    start = time.time()
    result = multi_layer_validate(email)
    elapsed = (time.time() - start) * 1000  # Convert to ms
    
    print(f"\n{email}")
    print(f"  Status: {result['status']}")
    print(f"  Reason: {result['reason']}")
    print(f"  Time: {elapsed:.1f}ms")


# Test 2: Bulk validation with mixed emails
print("\n\n[TEST 2] Bulk Validation Performance")
print("-" * 80)

# Create a larger test set
bulk_test = []
bulk_test.extend(["invalid@" for _ in range(100)])  # 100 invalid syntax
bulk_test.extend([f"test{i}@guerrillamail.com" for i in range(100)])  # 100 disposable
bulk_test.extend([f"user{i}@gmail.com" for i in range(200)])  # 200 free providers
bulk_test.extend([f"test{i}@yahoo.com" for i in range(100)])  # 100 free providers

print(f"\nTesting {len(bulk_test)} emails...")
print(f"Target: ~{len(bulk_test)/67:.1f}s (based on 67 emails/sec target)")

start = time.time()
results = bulk_validate_local(bulk_test[:500])  # Test with 500 emails first
elapsed = time.time() - start

# Calculate stats
valid_count = sum(1 for r in results if r.get('status') == 'VALID')
invalid_count = sum(1 for r in results if r.get('status') == 'INVALID')
risky_count = sum(1 for r in results if r.get('status') == 'RISKY')

print(f"\n\nRESULTS:")
print(f"  Total emails: {len(results)}")
print(f"  Valid: {valid_count}")
print(f"  Invalid: {invalid_count}")
print(f"  Risky: {risky_count}")
print(f"  Total time: {elapsed:.2f}s")
print(f"  Average: {(elapsed/len(results))*1000:.1f}ms per email")
print(f"  Speed: {len(results)/elapsed:.1f} emails/second")

# Projection for 2000 emails
projected_time = (2000 / len(results)) * elapsed
print(f"\n  📊 PROJECTED TIME FOR 2000 EMAILS: {projected_time:.1f}s")

if projected_time < 30:
    print(f"  ✅ PASS - Under 30 second target!")
else:
    print(f"  ❌ NEEDS OPTIMIZATION - {projected_time - 30:.1f}s over target")

print("\n" + "="*80)
