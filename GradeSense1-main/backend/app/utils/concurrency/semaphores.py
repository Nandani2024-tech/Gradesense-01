"""Semaphore factory and registry."""

import asyncio
from typing import Dict
from .limits import PDF_CONVERSION_LIMIT

# Internal registry of semaphores to ensure they are singletons per resource
_semaphores: Dict[str, asyncio.Semaphore] = {}

def get_semaphore(resource_name: str, limit: int = 1) -> asyncio.Semaphore:
    """
    Get or create an asyncio.Semaphore for a specific resource.
    
    Args:
        resource_name: A unique name for the resource.
        limit: The concurrency limit for this resource.
        
    Returns:
        An asyncio.Semaphore for the resource.
    """
    if resource_name not in _semaphores:
        _semaphores[resource_name] = asyncio.Semaphore(max(1, limit))
    return _semaphores[resource_name]

# Backward Compatibility - existing conversion_semaphore
_conversion_limit = PDF_CONVERSION_LIMIT
conversion_semaphore = get_semaphore("pdf_conversion", _conversion_limit)

# How to add new semaphores:
# To add a new resource semaphore, simply call get_semaphore("resource_name", limit)
# where limit can be loaded from limits.py.
