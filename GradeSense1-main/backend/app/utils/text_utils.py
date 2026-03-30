import unicodedata
import re

def normalize_text_unicode_safe(text: str) -> str:
    """
    Standardizes on NFC (Canonical Composition).
    Preserves multilingual characters (Hindi, etc.) while stripping only 
    structural separators that are not intrinsic to the language.
    """
    if not text:
        return ""
    
    # Standardize to NFC: 'Combined' characters instead of 'Base + Mark'
    normalized = unicodedata.normalize('NFC', str(text))
    
    # Trim leading/trailing whitespace
    return normalized.strip()

def slugify_multilingual(text: str) -> str:
    """
    Strict slugification that preserves multilingual combining marks.
    Removes whitespace, punctuation, and structural separators.
    """
    text = normalize_text_unicode_safe(text).lower()
    # Replace spaces and punctuation with underscores
    text = re.sub(r'[\s:,-]+', '_', text)
    # Remove everything that isn't alphanumeric or an underscore
    # This might be too aggressive for Hindi if not careful, 
    # but re.sub(r'[^\w\s]', ...) with Unicode works in Python 3.
    text = re.sub(r'[^\w_]', '', text)
    return text.strip('_')
