from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime

# --- Pydantic Schemas (Internal Data Contract) --- #

class ExperienceSchema(BaseModel):
    company: str
    role: str
    duration: str
    achievements: List[str]

class ExtractedResumeSchema(BaseModel):
    name: str = Field(..., description="Full name of the candidate")
    email: str = Field(..., description="Valid email address")
    phone: str = Field(..., description="Contact phone number")
    skills: List[str] = Field(..., description="Technical and soft skills")
    experience: List[ExperienceSchema]
    education: List[str]
    summary: str = Field(..., description="Professional summary of the candidate")

class ExtractedJDSchema(BaseModel):
    title: str
    required_skills: List[str]
    preferred_experience_years: Optional[int]
    responsibilities: List[str]
    key_competencies: List[str]

# --- Database Response Models (What frontend sees) --- #

class CandidateBase(BaseModel):
    name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    created_at: datetime

class CandidateFull(CandidateBase):
    id: int
    extracted_resume_json: Optional[Dict[str, Any]]
    jd_json: Optional[Dict[str, Any]]
    interview_transcript: Optional[str]
    
    class Config:
        from_attributes = True
