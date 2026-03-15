import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

def setup_cors(app: FastAPI):
    """Setup CORS middleware for the application"""
    cors_origins_env = os.environ.get("CORS_ORIGINS")
    cors_origins = [origin.strip() for origin in cors_origins_env.split(",")] if cors_origins_env else [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://wssbbmfb-3000.inc1.devtunnels.ms",
    ]

    # Also accept any devtunnels.ms origin dynamically
    FRONTEND_URL = os.environ.get("FRONTEND_URL", "")
    if FRONTEND_URL:
        cors_origins.append(FRONTEND_URL)

    app.add_middleware(
        CORSMiddleware,
        allow_credentials=True,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
