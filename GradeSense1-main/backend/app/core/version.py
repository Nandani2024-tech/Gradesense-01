import os
import logging

logger = logging.getLogger("gradesense")

def get_version_info():
    """Get deployment version information."""
    git_commit = os.environ.get("GIT_COMMIT_SHA")
    if not git_commit:
        try:
            if os.path.exists(".git_commit"):
                with open(".git_commit", "r") as f:
                    git_commit = f.read().strip()
        except Exception:
            pass

    if not git_commit:
        logger.warning("GIT_COMMIT_SHA not set and .git_commit not found. Build pipeline issue?")
        git_commit = "unknown"

    build_time = os.environ.get("BUILD_TIME", "unknown")
    env = os.environ.get("ENV", os.environ.get("ENVIRONMENT", "development"))

    return {
        "git_commit": git_commit,
        "build_time": build_time,
        "environment": env
    }
