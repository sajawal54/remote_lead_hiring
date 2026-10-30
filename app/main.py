from fastapi import FastAPI
from app.api.v1.api import api_router
from app.core.database import engine, Base
from app.models.models import WorkSpaceModel, WorkFlowExecutionModel, JobLeadModel


Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Remote Hiring Lead Intelligence Platform",
    version="1.0.0",
    description="Backend API implementing the agentic system reference design."
)

# API v1 routers ko include karna
app.include_router(api_router, prefix="/api/v1")

@app.get("/")
def root():
    return {"message": "Remote Hiring Lead Intelligence API active hai", "status": "running"}