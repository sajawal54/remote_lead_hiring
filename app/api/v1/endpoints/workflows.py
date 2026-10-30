from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import WorkFlowExecutionModel, WorkSpaceModel

router = APIRouter()

class SearchCriteria(BaseModel):
    service_types: List[str]
    tech_stack: List[str]
    region: str
    remote_rules: str
    freshness_days: int
    min_score: int

@router.post("/workflows", status_code=201)
def create_workflow(criteria: SearchCriteria, db: Session = Depends(get_db)):
    """
    POST /workflows: User ki search criteria accept karta hai, 
    database mein workflow record create karta hai aur execution ID return karta hai.
    """
    # 1. Pehle ensure karein ke mock workspace database mein mojood ho (Tenant isolation check)
    workspace_id = "ws_mock_tenant_a"
    workspace = db.query(WorkSpaceModel).filter(WorkSpaceModel.workspace_id == workspace_id).first()
    if not workspace:
        workspace = WorkSpaceModel(workspace_id=workspace_id, name="Default Test Workspace")
        db.add(workspace)
        db.commit()

    # 2. Unique workflow ID generate karna
    workflow_id = "wf_exec_" + str(abs(hash(str(criteria))))[:8]

    # 3. Database mein workflow execution record save karna
    db_workflow = WorkFlowExecutionModel(
        workflow_id=workflow_id,
        workspace_id=workspace_id,
        status="queued",
        stage="source_selection",
        criteria=criteria.dict()
    )
    db.add(db_workflow)
    db.commit()
    db.refresh(db_workflow)

    return {
        "workflow_id": db_workflow.workflow_id,
        "workspace_id": db_workflow.workspace_id,
        "status": db_workflow.status,
        "acceptedAt": db_workflow.created_at
    }

@router.get("/workflows/{workflow_id}")
def get_workflow_status(workflow_id: str, db: Session = Depends(get_db)):
    """
    GET /workflows/{id}: Database se workflow ka current state fetch karta hai.
    """
    workflow = db.query(WorkFlowExecutionModel).filter(WorkFlowExecutionModel.workflow_id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow execution not found")
    
    return {
        "workflow_id": workflow.workflow_id,
        "status": workflow.status,
        "stage": workflow.stage,
        "created_at": workflow.created_at
    }