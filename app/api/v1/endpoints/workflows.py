from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from app.services.orchestrator import initialize_workflow_execution
from app.services.background_worker import process_workflow_job
from app.core.database import get_db
from app.core.security import verify_access_token
from app.models.models import WorkflowExecutionModel, WorkflowStepModel
from app.schemas.workflow import WorkflowRequest

router = APIRouter(prefix="/workflows", tags=["Workflows"])

@router.post("")
def create_workflow(
    search_criteria: WorkflowRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(verify_access_token),
    db: Session = Depends(get_db)
):
    """
    Creates a durable workflow execution and triggers asynchronous pipeline processing.
    PDF Section 15: POST /workflows
    """
    workspace_id = current_user["workspace_id"]
    criteria = search_criteria.model_dump(exclude_none=True)
    if (
        criteria.get("salary_min") is not None
        and criteria.get("salary_max") is not None
        and criteria["salary_min"] > criteria["salary_max"]
    ):
        raise HTTPException(status_code=422, detail="salary_min cannot exceed salary_max.")

    result = initialize_workflow_execution(db, workspace_id=workspace_id, criteria=criteria)
    workflow_id = result.get("workflow_id")
    if not workflow_id:
        raise HTTPException(status_code=500, detail="Workflow could not be initialized.")

    # Add background task for asynchronous pipeline execution
    background_tasks.add_task(
        process_workflow_job,
        workflow_id=workflow_id,
        workspace_id=workspace_id
    )

    return {
        "status": "queued",
        "workflow_id": workflow_id,
        "workspace_id": workspace_id,
        "message": "Workflow created successfully. Pipeline processing running in background."
    }

@router.get("/{workflow_id}")
def get_workflow_status(
    workflow_id: str,
    current_user: dict = Depends(verify_access_token),
    db: Session = Depends(get_db)
):
    """
    Retrieves workflow status and current stage.
    PDF Section 15: GET /workflows/{id}
    """
    execution = db.query(WorkflowExecutionModel).filter(
        WorkflowExecutionModel.id == workflow_id,
        WorkflowExecutionModel.workspace_id == current_user["workspace_id"]
    ).first()

    if not execution:
        raise HTTPException(status_code=404, detail="Workflow execution not found.")

    steps = db.query(WorkflowStepModel).filter(
        WorkflowStepModel.workflow_id == workflow_id,
        WorkflowStepModel.workspace_id == current_user["workspace_id"],
    ).order_by(WorkflowStepModel.created_at.asc()).all()

    return {
        "workflow_id": execution.id,
        "workspace_id": execution.workspace_id,
        "status": execution.status,
        "stage": execution.stage,
        "created_at": execution.created_at,
        "finished_at": execution.finished_at,
        "last_error": execution.last_error_code,
        "steps": [
            {
                "stage": step.stage,
                "status": step.status,
                "attempt": step.attempt,
                "decision_reason": step.decision_reason,
                "created_at": step.created_at,
            }
            for step in steps
        ],
    }