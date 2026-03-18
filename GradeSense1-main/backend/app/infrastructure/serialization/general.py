"""General serialization helpers for recursive data structures."""

from typing import Any, List, Dict, Callable

def recursive_serialize(data: Any, custom_serializer: Callable[[Any], Any] = None) -> Any:
    """
    Recursively serialize lists and dictionaries.
    
    Args:
        data: The data to serialize.
        custom_serializer: An optional function to handle custom types.
        
    Returns:
        The serialized data.
    """
    if custom_serializer:
        result = custom_serializer(data)
        if result is not data:
            return result

    if isinstance(data, list):
        return [recursive_serialize(item, custom_serializer) for item in data]
    
    if isinstance(data, dict):
        return {key: recursive_serialize(value, custom_serializer) for key, value in data.items()}
    
    return data
