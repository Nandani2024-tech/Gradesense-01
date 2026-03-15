# Task Worker constants

# Task Types
TASK_TYPE_GRADE_PAPER = "grade_paper"
STRICT_EXAM_TYPE_REGEX = "^college$"

# Task Statuses
TASK_STATUS_PENDING = "pending"
TASK_STATUS_PROCESSING = "processing"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"

# Worker Config
WORKER_POLL_INTERVAL_SECONDS = 15  # Polling interval for idle loop
STALE_TASK_THRESHOLD_MINUTES = 30  # Time before an In-Progress task is considered stale
STRICT_EXAM_TIMEOUT_MINUTES = 45   # Timeout for strict exam processing
