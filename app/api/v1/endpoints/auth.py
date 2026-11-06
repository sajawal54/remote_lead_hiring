from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import WorkspaceModel, UserModel
from app.core.security import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["Authentication & Security"])


class SignupRequest(BaseModel):
    email: str = Field(min_length=1, examples=["user@example.com"])
    password: str = Field(min_length=1)
    workspace_name: str = Field(min_length=1, examples=["My Workspace"])


class SigninRequest(BaseModel):
    email: str = Field(min_length=1, examples=["user@example.com"])
    password: str = Field(min_length=1)


@router.post("/signup")
def signup_workspace(payload: SignupRequest, db: Session = Depends(get_db)):
    """
    Registers a new workspace tenant and admin user, returning a signed JWT access token.
    """
    email = payload.email.strip().lower()
    password = payload.password
    workspace_name = payload.workspace_name.strip()
    if not email or not password or not workspace_name:
        raise HTTPException(status_code=400, detail="Email, password, and workspace name cannot be empty.")

    existing_user = db.query(UserModel).filter(UserModel.email == email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User with this email already exists.")

    try:
        ws = WorkspaceModel(name=workspace_name)
        db.add(ws)
        db.flush()

        user = UserModel(
            workspace_id=ws.id,
            email=email,
            hashed_password=hash_password(password),
            role="workspace_admin",
        )
        db.add(user)
        db.commit()
    except Exception:
        db.rollback()
        raise

    # Generate JWT Token
    access_token = create_access_token(data={"sub": email, "workspace_id": ws.id})

    return {
        "status": "success",
        "workspace_id": ws.id,
        "access_token": access_token,
        "token_type": "bearer",
        "message": "Workspace registered successfully with secure JWT authentication."
    }

@router.post("/signin")
def signin_workspace(payload: SigninRequest, db: Session = Depends(get_db)):
    """
    Authenticates user credentials and returns a secure JWT access token.
    """
    email = payload.email.strip().lower()
    password = payload.password

    user = db.query(UserModel).filter(UserModel.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    # Generate JWT Token
    access_token = create_access_token(data={"sub": user.email, "workspace_id": user.workspace_id})

    return {
        "status": "success",
        "workspace_id": user.workspace_id,
        "access_token": access_token,
        "token_type": "bearer",
        "message": "Signed in successfully."
    }