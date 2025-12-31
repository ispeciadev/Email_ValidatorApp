#!/usr/bin/env python3
"""Test script for email validation improvements"""

import sys
sys.path.insert(0, '/home/Abhi/Downloads/Email_ValidatorApp-main/backend')

from validator.fast_validator import check_disposable_fast, check_syntax_fast, check_role_fast

print("=== EMAIL VALIDATION ACCURACY TESTS ===")
print()

# Test 1: Disposable detection with subdomain matching
print("--- DISPOSABLE DETECTION ---")
test_cases = [
    ('tempmail.com', True),
    ('xyz.tempmail.com', True),  # subdomain
    ('guerrillamail.com', True),
    ('yopmail.com', True),
    ('gmail.com', False),  # Should NOT be disposable
    ('outlook.com', False),  # Should NOT be disposable
    ('mytempmailservice.com', True),  # pattern match
]

all_passed = True
for domain, expected in test_cases:
    result = check_disposable_fast(domain)
    status = "✓" if result == expected else "✗"
    if result != expected:
        all_passed = False
    print(f"  {status} {domain}: {'DISPOSABLE' if result else 'OK'} (expected: {'DISPOSABLE' if expected else 'OK'})")

print()

# Test 2: Syntax validation
print("--- SYNTAX VALIDATION ---")
syntax_tests = [
    ('valid@gmail.com', True),
    ('user+tag@gmail.com', True),  # plus addressing
    ('invalid..email@test.com', False),  # consecutive dots
]
for email, expected in syntax_tests:
    is_valid, reason, _, _ = check_syntax_fast(email)
    status = "✓" if is_valid == expected else "✗"
    print(f"  {status} {email}: {'VALID' if is_valid else f'INVALID ({reason})'}")

print()

# Test 3: Role-based detection
print("--- ROLE DETECTION ---")
role_tests = [
    ('admin', True),
    ('info', True),
    ('support', True),
    ('john', False),
    ('noreply', True),
]
for local, expected in role_tests:
    result = check_role_fast(local)
    status = "✓" if result == expected else "✗"
    print(f"  {status} {local}@example.com: {'ROLE' if result else 'PERSONAL'}")

print()
if all_passed:
    print("=== ALL TESTS PASSED ===")
else:
    print("=== SOME TESTS FAILED ===")
