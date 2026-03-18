"""Legacy behavior and backward compatibility support."""

from .mongo import serialize_doc as _serialize_doc

def serialize_doc(doc):
    """Legacy wrapper for serialize_doc."""
    return _serialize_doc(doc)
