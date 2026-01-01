"""
SMTP Connection Pool Manager
Manages domain-based SMTP connection pools with connection reuse
"""
import asyncio
import aiosmtplib
import random
from typing import List, Optional, Dict, Any

class SMTPConnectionPool:
    """
    Connection pool for a single domain
    Maintains 2-4 reusable SMTP connections
    """
    
    def __init__(self, domain: str, mx_hosts: List[str], max_size: int = 3):
        self.domain = domain
        self.mx_hosts = mx_hosts
        self.max_size = max_size
        self.pool: List[aiosmtplib.SMTP] = []
        self.lock = asyncio.Lock()
        self.probe_email = "verify@mail-validator.com"  # Sender for verification
    
    async def verify_email(self, email: str) -> Dict[str, Any]:
        """
        Verify email deliverability using SMTP
        Reuses connection from pool or creates new one
        """
        conn = None
        try:
            # Get connection
            conn = await self._acquire_connection()
            
            # SMTP verification flow
            # MAIL FROM
            await asyncio.wait_for(
                conn.mail(self.probe_email),
                timeout=2.0
            )
            
            # RCPT TO (this is the actual test)
            code, message = await asyncio.wait_for(
                conn.rcpt(email),
                timeout=2.0
            )
            
            # RSET (clear state for next email - very important!)
            await conn.rset()
            
            # Return to pool
            await self._release_connection(conn)
            
            return {
                "code": code,
                "message": message.decode() if isinstance(message, bytes) else str(message),
                "status": self._interpret_code(code)
            }
            
        except asyncio.TimeoutError:
            if conn:
                await self._close_connection(conn)
            return {"code": 0, "status": "timeout", "message": "SMTP timeout"}
        
        except Exception as e:
            if conn:
                await self._close_connection(conn)
            return {"code": 0, "status": "error", "message": str(e)}
    
    async def _acquire_connection(self) -> aiosmtplib.SMTP:
        """Get connection from pool or create new one"""
        async with self.lock:
            # Try to reuse existing connection
            while self.pool:
                conn = self.pool.pop(0)
                if await self._is_healthy(conn):
                    return conn
                else:
                    # Connection dead, close it
                    await self._close_connection(conn)
            
            # No healthy connection, create new
            return await self._create_connection()
    
    async def _release_connection(self, conn: aiosmtplib.SMTP):
        """Return connection to pool"""
        async with self.lock:
            if len(self.pool) < self.max_size:
                self.pool.append(conn)
            else:
                # Pool full, close connection
                await self._close_connection(conn)
    
    async def _create_connection(self) -> aiosmtplib.SMTP:
        """Create new SMTP connection to MX hosts"""
        last_error = None
        
        # Try each MX host in order
        for mx_host in self.mx_hosts:
            try:
                # Create client
                smtp = aiosmtplib.SMTP(
                    hostname=mx_host,
                    port=25,
                    timeout=2.0,
                    use_tls=False,  # Start without TLS
                    start_tls=False  # Don't upgrade
                )
                
                # Connect with timeout
                await asyncio.wait_for(smtp.connect(), timeout=2.0)
                
                # EHLO
                await smtp.ehlo()
                
                return smtp
                
            except Exception as e:
                last_error = e
                continue
        
        # All MX hosts failed
        raise Exception(f"All MX hosts failed for {self.domain}: {last_error}")
    
    async def _is_healthy(self, conn: aiosmtplib.SMTP) -> bool:
        """Check if connection is still alive"""
        try:
            if not conn.is_connected:
                return False
            # Try NOOP to test connection
            await asyncio.wait_for(conn.noop(), timeout=1.0)
            return True
        except:
            return False
    
    async def _close_connection(self, conn: aiosmtplib.SMTP):
        """Close SMTP connection safely"""
        try:
            if conn.is_connected:
                await conn.quit()
        except:
            pass  # Already closed
    
    def _interpret_code(self, code: int) -> str:
        """Interpret SMTP response code"""
        if code == 250:
            return "accepted"
        elif code in [550, 551, 553]:
            return "mailbox_not_found"
        elif code in [452, 552]:
            return "mailbox_full"
        elif code in [450, 451, 421]:
            return "temporary"
        else:
            return f"code_{code}"
    
    async def verify_fake_email(self) -> bool:
        """
        Test with fake email for catch-all detection
        Returns True if fake email is accepted (catch-all)
        """
        fake_local = f"nonexistent{random.randint(100000, 999999)}"
        fake_email = f"{fake_local}@{self.domain}"
        
        result = await self.verify_email(fake_email)
        
        # If fake email returns 250, it's catch-all
        return result.get("code") == 250
    
    async def close_all(self):
        """Close all connections in pool"""
        async with self.lock:
            for conn in self.pool:
                await self._close_connection(conn)
            self.pool.clear()
