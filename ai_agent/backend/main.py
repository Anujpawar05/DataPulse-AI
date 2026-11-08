from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai_agent.backend.routes.ask import router as ask_router
from ai_agent.backend.routes.analytics import router as analytics_router


app = FastAPI(
    title="DataPulse AI",
    description="AI-powered business intelligence assistant",
    version="1.0.0",
)

# CORS configuration for local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:8080",
        "http://localhost:8080",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/")
def root():
    return {
        "message": "Welcome to DataPulse AI",
        "status": "running",
        "version": "1.0.0",
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "DataPulse AI Agent",
    }


app.include_router(ask_router)
app.include_router(analytics_router)