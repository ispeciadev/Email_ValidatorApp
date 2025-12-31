import bcrypt

# Your desired admin credentials
email = "ssharma636076@gmail.com"
password = "Shiva@123"

# Generate bcrypt hash
hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
hashed_str = hashed.decode()

print("=" * 60)
print("ADMIN ACCOUNT CREATION")
print("=" * 60)
print(f"\nEmail: {email}")
print(f"Password: {password}")
print(f"\nBcrypt Hash: {hashed_str}")
print("\n" + "=" * 60)
print("SQL QUERY TO CREATE ADMIN:")
print("=" * 60)
print(f"""
INSERT INTO users (email, hashed_password, name, role, credits, blocked, status)
VALUES (
    '{email}',
    '{hashed_str}',
    'Admin User',
    'admin',
    999999,
    false,
    'active'
)
ON CONFLICT (email) DO UPDATE SET
    hashed_password = EXCLUDED.hashed_password,
    role = 'admin',
    status = 'active',
    blocked = false;
""")
print("=" * 60)
print("\nCopy the SQL above and run it in pgAdmin!")
print("=" * 60)
