#!/usr/bin/env python3
"""
Benchmark script for Strict Email Validator
Tests performance after optimizations
"""

import asyncio
import time
import sys
sys.path.insert(0, 'validator')

from strict_validator import StrictEmailValidator, validate_syntax

# Test emails for benchmark
TEST_EMAILS = [
    # Invalid syntax (instant reject)
    "invalid",
    "@nodomain.com",
    "bad..dots@test.com",
    "double@@at.com",
    "",
    "no-at-sign.com",
    
    # Valid syntax but non-existent domains (DNS check)
    "user@nonexistent-domain-xyz123.com",
    "test@fake-domain-abc789.com",
    "admin@not-a-real-domain.xyz",
    
    # Real domains (DNS + potentially SMTP)
    "test@gmail.com",
    "test@yahoo.com",
    "test@outlook.com",
    "test@hotmail.com",
    "test@aol.com",
    "info@google.com",
    "contact@microsoft.com",
    "support@apple.com",
]

async def benchmark_single():
    """Benchmark single email validation"""
    validator = StrictEmailValidator()
    await validator.initialize()
    
    print("\n=== Single Email Validation Benchmark ===")
    
    total_time = 0
    for email in TEST_EMAILS[:10]:  # First 10
        start = time.time()
        result = await validator.validate_email(email)
        elapsed = time.time() - start
        total_time += elapsed
        print(f"  {email:<40} -> {result['status']:<8} ({elapsed:.3f}s)")
    
    print(f"\n  Average: {total_time/10:.3f}s per email")
    return total_time / 10

async def benchmark_bulk():
    """Benchmark bulk email validation"""
    validator = StrictEmailValidator()
    await validator.initialize()
    
    print("\n=== Bulk Email Validation Benchmark ===")
    
    # Small batch
    start = time.time()
    results = await validator.validate_bulk(TEST_EMAILS)
    elapsed = time.time() - start
    rate = len(TEST_EMAILS) / elapsed
    print(f"  {len(TEST_EMAILS)} emails: {elapsed:.2f}s ({rate:.1f}/sec)")
    
    # Larger batch (duplicate emails to test caching)
    large_batch = TEST_EMAILS * 5  # 90 emails
    start = time.time()
    results = await validator.validate_bulk(large_batch)
    elapsed = time.time() - start
    # Note: unique count because of deduplication
    unique_count = len(set(large_batch))
    rate = unique_count / elapsed
    print(f"  {len(large_batch)} emails ({unique_count} unique): {elapsed:.2f}s ({rate:.1f}/sec)")
    
    return rate

async def benchmark_syntax_only():
    """Benchmark pure syntax validation (instant)"""
    print("\n=== Syntax-Only Benchmark (no network) ===")
    
    emails = TEST_EMAILS * 100  # 1800 emails
    
    start = time.time()
    for email in emails:
        validate_syntax(email)
    elapsed = time.time() - start
    
    rate = len(emails) / elapsed
    print(f"  {len(emails)} emails: {elapsed:.4f}s ({rate:.0f}/sec)")
    return rate

async def main():
    print("=" * 60)
    print("STRICT EMAIL VALIDATOR - PERFORMANCE BENCHMARK")
    print("=" * 60)
    
    print("\nConfiguration:")
    from strict_validator import (
        CONNECTION_TIMEOUT, READ_TIMEOUT, DNS_TIMEOUT,
        MAX_CONCURRENT_SMTP, MAX_CONCURRENT_DNS, MAX_MX_PARALLEL
    )
    print(f"  CONNECTION_TIMEOUT: {CONNECTION_TIMEOUT}s")
    print(f"  READ_TIMEOUT: {READ_TIMEOUT}s")
    print(f"  DNS_TIMEOUT: {DNS_TIMEOUT}s")
    print(f"  MAX_CONCURRENT_SMTP: {MAX_CONCURRENT_SMTP}")
    print(f"  MAX_CONCURRENT_DNS: {MAX_CONCURRENT_DNS}")
    print(f"  MAX_MX_PARALLEL: {MAX_MX_PARALLEL}")
    
    # Run benchmarks
    syntax_rate = await benchmark_syntax_only()
    avg_single = await benchmark_single()
    bulk_rate = await benchmark_bulk()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Syntax-only throughput: {syntax_rate:.0f} emails/sec")
    print(f"  Single validation avg:  {avg_single:.3f}s")
    print(f"  Bulk validation rate:   {bulk_rate:.1f} unique emails/sec")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
