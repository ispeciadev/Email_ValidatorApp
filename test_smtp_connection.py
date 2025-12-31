import asyncio
import aiosmtplib
import socket

async def test_connection():
    mx_host = "gmail-smtp-in.l.google.com"
    port = 25
    print(f"Attempting to connect to {mx_host}:{port}...")
    
    try:
        # Resolve IP first
        ip = socket.gethostbyname(mx_host)
        print(f"Resolved {mx_host} to {ip}")
        
        # Test Socket connection first (basic TCP)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        result = sock.connect_ex((ip, port))
        if result == 0:
            print("Successfully connected via TCP socket!")
            sock.close()
        else:
            print(f"TCP socket connection failed with error code: {result}")
            return

        # Test SMTP protocol FULL FLOW
        print("Starting full SMTP handshake...")
        smtp = aiosmtplib.SMTP(hostname=mx_host, port=port, timeout=5.0)
        await smtp.connect()
        print("Connected!")
        
        print("Sending EHLO...")
        await smtp.ehlo()
        print("EHLO success!")
        
        print("Sending MAIL FROM...")
        await smtp.mail("validator@mail-validator.com")
        print("MAIL FROM success!")
        
        print("Sending RCPT TO (testing ssharma636076@gmail.com)...")
        response = await smtp.rcpt("ssharma636076@gmail.com")
        print(f"RCPT TO result: {response}")
        
        await smtp.quit()
        print("Full verification cycle successful!")

    except Exception as e:
        print(f"Connection failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(test_connection())
