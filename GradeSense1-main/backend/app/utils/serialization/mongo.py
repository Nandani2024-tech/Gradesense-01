"""Core MongoDB serialization logic."""

from bson import ObjectId
from typing import Any, Optional
from .general import recursive_serialize

def mongo_serializer(obj: Any) -> Any:
    """Handle MongoDB specific types like ObjectId."""
    if isinstance(obj, ObjectId):
        return str(obj)
    return obj

def serialize_doc(doc: Any) -> Any:
    """
    Convert MongoDB document to JSON-safe dict.
    Skips '_id' at the top level and handles recursion.
    """
    if doc is None:
        return None
    
    if isinstance(doc, ObjectId):
        return str(doc)
        
    if isinstance(doc, list):
        return [serialize_doc(d) for d in doc]
        
    if isinstance(doc, dict):
        result = {}
        for key, value in doc.items():
            if key == "_id":
                continue
            
            # Handle the value recursively
            if isinstance(value, ObjectId):
                result[key] = str(value)
            elif isinstance(value, (dict, list)):
                result[key] = serialize_doc(value)
            else:
                result[key] = value
        return result
        
    return doc
