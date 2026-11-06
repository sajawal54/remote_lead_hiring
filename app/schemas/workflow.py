from pydantic import BaseModel, ConfigDict, Field


class WorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    tech_stack: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    region: str | None = None
    countries: list[str] = Field(default_factory=list)
    remote_only: bool = False
    min_score: int = Field(default=0, ge=0, le=100)
    max_age_days: int = Field(default=14, ge=1, le=365)
    seniority: list[str] = Field(default_factory=list)
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    source_names: list[str] = Field(default_factory=list)
