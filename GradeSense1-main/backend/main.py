from fastapi import FastAPI
from app.core.config import load_dotenv # Ensures .env is loaded early
from app.startup.lifespan import lifespan
from app.middleware.cors import setup_cors
from app.middleware.metrics import setup_metrics
from app.routes import register_all_routes

app = FastAPI(
    title="GradeSense API",
    lifespan=lifespan
)

setup_cors(app)
setup_metrics(app)

register_all_routes(app)
