import smtplib
import dns.resolver
import socket

# SMTP timeout - aggressive for speed (was 10s, now 2s)
SMTP_TIMEOUT = 2

# Trusted providers that block SMTP - skip verification
TRUSTED_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com",
    "yahoo.com", "yahoo.co.uk", "icloud.com", "me.com", "aol.com",
    "protonmail.com", "zoho.com", "fastmail.com", "yandex.com"
})

def verify_smtp(email: str) -> bool:
    try:
        domain = email.split('@')[1]
        
        # Skip SMTP for trusted providers (they block it)
        if domain.lower() in TRUSTED_DOMAINS:
            # Just verify MX exists
            try:
                records = dns.resolver.resolve(domain, 'MX')
                return len(records) > 0
            except Exception:
                return False
        
        records = dns.resolver.resolve(domain, 'MX')
        mx_record = str(records[0].exchange)

        server = smtplib.SMTP(timeout=SMTP_TIMEOUT)
        server.connect(mx_record)
        server.helo()
        server.mail('check@example.com')
        code, _ = server.rcpt(email)
        server.quit()

        return code == 250
    except Exception:
        return False
