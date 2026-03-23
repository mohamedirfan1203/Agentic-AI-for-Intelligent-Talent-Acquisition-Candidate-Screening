"""
Upload Routes
=============
Single endpoint: upload resume + JD together.
The OrchestratorAgent handles extraction and screening in one pass.

Endpoint
--------
POST /upload/resume-and-jd  — upload resume + job description together
"""

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from agents.orchestrator.agent import orchestrator_agent

logger = logging.getLogger("app.routes.upload")

router = APIRouter(prefix="/upload", tags=["Upload"])


@router.post(
    "/resume-and-jd",
    summary="Upload candidate resume + job description",
    response_description="Extraction and screening results for the uploaded documents",
)
async def upload_resume_and_jd(
    resume_file: UploadFile = File(..., description="Candidate resume (PDF/DOCX/TXT)"),
    jd_file: UploadFile = File(..., description="Job description (PDF/DOCX/TXT)"),
    db: Session = Depends(get_db),
):
    """
    Accepts a candidate's resume and a job description in one request.

    Internally runs:
    1. **ExtractionAgent** — parses and structures both documents
    2. **ScreeningAgent**  — scores the candidate against the JD
    3. **GmailAgent**      — sends shortlisting or rejection email

    The candidate record (with extracted data + screening scorecard) is saved
    to the database and returned in the response.
    """
    logger.info(
        f"[Route] POST /upload/resume-and-jd — "
        f"resume={resume_file.filename} | jd={jd_file.filename}"
    )
    resume_content = await resume_file.read()
    jd_content = await jd_file.read()

    if not resume_content:
        raise HTTPException(status_code=400, detail="Resume file is empty.")
    if not jd_content:
        raise HTTPException(status_code=400, detail="JD file is empty.")

    try:
        result = orchestrator_agent.run(
            db=db,
            resume_content=resume_content,
            resume_filename=resume_file.filename,
            jd_content=jd_content,
            jd_filename=jd_file.filename,
        )
    except Exception as exc:
        logger.error(f"[Route] Orchestrator error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    return result
