import hashlib
import json

def get_model_answer_hash(images):
    """SHA256 hash for model answer images."""
    image_hashes = [hashlib.sha256(img.encode()).hexdigest() for img in images]
    return hashlib.sha256(json.dumps(image_hashes).encode()).hexdigest()
