import time
import asyncio
from fastapi import FastAPI, Request
from app.core.logging_config import logger
from app.services.metrics.metrics_service import log_api_metric

def setup_metrics(app: FastAPI):
    """Setup metrics tracking middleware for the application"""
    @app.middleware("http")
    async def metrics_tracking_middleware(request: Request, call_next):
        """Track API metrics for all requests"""
        start_time = time.time()

        user_id = None
        try:
            if request.url.path != "/api/auth/me":
                auth_header = request.headers.get("cookie", "")
                if "session" in auth_header:
                    pass
        except:
            pass

        response = None
        error_type = None
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            error_type = type(e).__name__
            status_code = 500
            logger.error(f"Request failed: {str(e)}")
            raise
        finally:
            response_time_ms = int((time.time() - start_time) * 1000)

            asyncio.create_task(log_api_metric(
                endpoint=request.url.path,
                method=request.method,
                response_time_ms=response_time_ms,
                status_code=status_code,
                error_type=error_type,
                user_id=user_id,
                ip_address=request.client.host if request.client else None
            ))

        return response
