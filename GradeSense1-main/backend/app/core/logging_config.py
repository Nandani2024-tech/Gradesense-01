import logging

def initialize_logging():
    """Configure logging globally."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Disable noisy logging from libraries to prevent console scrambling
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("google-genai").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

# Initialize logger for this module
logger = logging.getLogger("gradesense")

# Automatically initialize when imported if needed, 
# but the task asks for a function initialize_logging() to be called.
# We'll expose the logger as requested.
