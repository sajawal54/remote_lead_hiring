from pydantic import BaseModel
from typing import List , Optional

class SalaryInfo(BaseModel):
  min: Optional[float] = None
  max: Optional[float] = None
  currency: Optional[str] = "USD"
  period: Optional[str] = "year"
  
class ScoreBreakdown(BaseModel):
  relevance : int
  hiring_intent : int
  freshness : int
  remote_fit : int
  salary_value : int
  company_activity : int
  seniority : int
  data_quality : int
  total_score : int
  
class LeadResponse(BaseModel):
  job_id : str
  company_name : str
  title : str
  location : str
  remote_policy : str
  allowed_countries : List[str]
  technologies : List[str]
  salary : Optional[SalaryInfo] = None
  score_breakdown : ScoreBreakdown
  last_verified_at : str
  sources_count : int