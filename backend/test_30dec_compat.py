import asyncio
import json
from validator.async_validator import validate_email_async

async def test_format():
    test_emails = [
        "hi@gmail.com",        # Valid (Free provider)
        "test@example.com",     # Custom domain
        "admin@reoon.com",      # Role account
        "invalid@@syntax.com",  # Invalid syntax
        "disposable@mailinator.com" # Disposable
    ]
    
    print("\n" + "="*80)
    print("Testing 30 Dec Output Format Compatibility")
    print("="*80)
    
    for email in test_emails:
        print(f"\nProcessing: {email}")
        try:
            result = await validate_email_async(email)
            print(json.dumps(result, indent=2))
            
            # Verify critical legacy fields
            required_legacy = ["regex", "mx", "smtp", "role_based", "disposable", "blacklist", "catch_all", "verdict"]
            missing = [f for f in required_legacy if f not in result]
            if missing:
                print(f"❌ Missing legacy fields: {missing}")
            else:
                print(f"✅ Legacy fields present: {required_legacy}")
                
            # Verify status casing
            if result["status"] not in ["VALID", "INVALID", "RISKY", "NEUTRAL"]:
                print(f"❌ Status casing incorrect: {result['status']}")
            else:
                print(f"✅ Status casing correct: {result['status']}")
                
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_format())
