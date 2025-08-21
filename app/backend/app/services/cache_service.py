"""
Simple caching service for frequently accessed data.
Uses in-memory cache with TTL (Time To Live) for efficiency.
"""

import time
from typing import Any, Dict, Optional
from datetime import datetime, timedelta

class CacheService:
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        if key not in self._cache:
            return None
        
        cache_entry = self._cache[key]
        if time.time() > cache_entry['expires_at']:
            # Cache expired, remove it
            del self._cache[key]
            return None
        
        return cache_entry['value']
    
    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        """Set value in cache with TTL (default 5 minutes)."""
        self._cache[key] = {
            'value': value,
            'expires_at': time.time() + ttl_seconds,
            'created_at': time.time()
        }
    
    def invalidate(self, key: str) -> None:
        """Remove specific key from cache."""
        if key in self._cache:
            del self._cache[key]
    
    def clear(self) -> None:
        """Clear all cache."""
        self._cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            'total_entries': len(self._cache),
            'keys': list(self._cache.keys())
        }

# Global cache instance
cache_service = CacheService()
