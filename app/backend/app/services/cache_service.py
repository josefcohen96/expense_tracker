"""
Simple caching service for frequently accessed data.
Uses in-memory cache with TTL (Time To Live) for efficiency.
"""

import time
import logging
from typing import Any, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class CacheService:
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        logger.info(f"Cache GET request for key: {key}")
        
        if key not in self._cache:
            logger.info(f"Cache MISS for key: {key} (key not found)")
            return None
        
        cache_entry = self._cache[key]
        if time.time() > cache_entry['expires_at']:
            # Cache expired, remove it
            logger.info(f"Cache MISS for key: {key} (expired)")
            del self._cache[key]
            return None
        
        logger.info(f"Cache HIT for key: {key}, value type: {type(cache_entry['value'])}, value length: {len(cache_entry['value']) if hasattr(cache_entry['value'], '__len__') else 'N/A'}")
        return cache_entry['value']
    
    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        """Set value in cache with TTL (default 5 minutes)."""
        logger.info(f"Cache SET for key: {key}, value type: {type(value)}, value length: {len(value) if hasattr(value, '__len__') else 'N/A'}, TTL: {ttl_seconds}s")
        self._cache[key] = {
            'value': value,
            'expires_at': time.time() + ttl_seconds,
            'created_at': time.time()
        }
    
    def invalidate(self, key: str) -> None:
        """Remove specific key from cache."""
        logger.info(f"Cache INVALIDATE for key: {key}")
        if key in self._cache:
            del self._cache[key]
            logger.info(f"Cache key {key} removed")
        else:
            logger.info(f"Cache key {key} not found for invalidation")
    
    def clear(self) -> None:
        """Clear all cache."""
        logger.info(f"Cache CLEAR - removing {len(self._cache)} entries")
        self._cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        stats = {
            'total_entries': len(self._cache),
            'keys': list(self._cache.keys())
        }
        logger.info(f"Cache STATS: {stats}")
        return stats

# Global cache instance
cache_service = CacheService()
