"""
DNS Cache Layer
Async DNS resolution with TTL-based caching and provider fingerprinting
"""
import asyncio
import time
from typing import Dict, List, Optional, Any
import aiodns
from cachetools import TTLCache

class DNSCache:
    """
    Async DNS resolver with intelligent caching
    Resolves each domain only once
    """
    
    def __init__(self, cache_ttl: int = 3600):
        """
        Args:
            cache_ttl: Cache time-to-live in seconds (default 1 hour)
        """
        self.cache = TTLCache(maxsize=10000, ttl=cache_ttl)
        self.catchall_cache = TTLCache(maxsize=5000, ttl=cache_ttl)
        self.resolver = aiodns.DNSResolver(timeout=2.0)
        self.lock = asyncio.Lock()
    
    async def get_mx_records(self, domain: str) -> Optional[Dict[str, Any]]:
        """
        Get MX records for domain (cached)
        Returns: {"mx_hosts": [...], "provider": "google|microsoft|yahoo|custom"}
        """
        cache_key = f"mx:{domain}"
        
        # Check cache
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # Resolve MX records
        try:
            # Try MX records first
            mx_records = await self.resolver.query(domain, 'MX')
            
            # Sort by priority (lower = higher priority)
            mx_sorted = sorted(mx_records, key=lambda mx: mx.priority)
            mx_hosts = [mx.host.rstrip('.') for mx in mx_sorted]
            
            # Fingerprint provider
            provider = self._detect_provider(mx_hosts[0] if mx_hosts else "")
            
            result = {
                "mx_hosts": mx_hosts,
                "provider": provider
            }
            
            # Cache result
            self.cache[cache_key] = result
            return result
            
        except aiodns.error.DNSError as e:
            # Try A record fallback
            try:
                await self.resolver.query(domain, 'A')
                # Domain exists but has no MX, use domain itself
                result = {
                    "mx_hosts": [domain],
                    "provider": "custom"
                }
                self.cache[cache_key] = result
                return result
            except:
                # No MX and no A record
                self.cache[cache_key] = None
                return None
        
        except Exception as e:
            print(f"[DNS ERROR] {domain}: {e}")
            return None
    
    def _detect_provider(self, mx_host: str) -> str:
        """
        Fingerprint email provider by MX hostname
        Returns: google|microsoft|yahoo|proton|zoho|custom
        """
        mx_lower = mx_host.lower()
        
        # Google / Gmail
        if any(x in mx_lower for x in ['google', 'gmail', 'googlemail']):
            return "google"
        
        # Microsoft / Outlook / Hotmail
        if any(x in mx_lower for x in ['outlook', 'hotmail', 'microsoft', 'office365']):
            return "microsoft"
        
        # Yahoo
        if 'yahoo' in mx_lower or 'ymail' in mx_lower:
            return "yahoo"
        
        # Proton
        if 'proton' in mx_lower:
            return "proton"
        
        # Zoho
        if 'zoho' in mx_lower:
            return "zoho"
        
        # AOL
        if 'aol' in mx_lower:
            return "aol"
        
        # Fastmail
        if 'fastmail' in mx_lower:
            return "fastmail"
        
        # Unknown / custom
        return "custom"
    
    async def is_catch_all_domain(self, domain: str, smtp_pool) -> bool:
        """
        Detect if domain is catch-all
        Uses SMTP pool to test with fake email
        Caches result to avoid repeated checks
        """
        cache_key = f"catchall:{domain}"
        
        # Check cache
        if cache_key in self.catchall_cache:
            return self.catchall_cache[cache_key]
        
        # Test with fake email
        try:
            is_catchall = await smtp_pool.verify_fake_email()
            self.catchall_cache[cache_key] = is_catchall
            return is_catchall
        except:
            # If test fails, assume not catch-all (conservative)
            self.catchall_cache[cache_key] = False
            return False
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics"""
        return {
            "mx_cache_size": len(self.cache),
            "catchall_cache_size": len(self.catchall_cache)
        }
