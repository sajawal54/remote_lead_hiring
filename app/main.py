from fastapi import FastAPI , Request
from fastapi.responses import JSONResponse
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

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error",
                 "message": "There is an error occured in the system but the server is safe",
                 "details" : str(exc)})


@app.get("/")
def root():
    return {"message": "Remote Hiring Lead Intelligence API active hai", "status": "running"}