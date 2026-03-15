import os

def _env_flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")

AWS_PIPELINE_ENABLED = _env_flag("AWS_PIPELINE_ENABLED", "false")
AWS_PIPELINE_EXAM_TYPES = [
    item.strip().lower()
    for item in os.getenv("AWS_PIPELINE_EXAM_TYPES", "college").split(",")
    if item.strip()
]
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET", "")
AWS_TEXTRACT_ROLE_ARN = os.getenv("AWS_TEXTRACT_ROLE_ARN", "")
AWS_TEXTRACT_POLL_INTERVAL_SECS = int(os.getenv("AWS_TEXTRACT_POLL_INTERVAL_SECS", "2"))
AWS_TEXTRACT_POLL_TIMEOUT_SECS = int(os.getenv("AWS_TEXTRACT_POLL_TIMEOUT_SECS", "900"))
AWS_TEXTRACT_ENABLE_TABLES = _env_flag("AWS_TEXTRACT_ENABLE_TABLES", "false")
