"""
Interview Routes
================
Standalone REST API for the AI interview chatbot.
These routes are completely independent of the orchestrator.

Endpoints
---------
POST /interview/start
    Start a new interview session for a candidate.
    Body: { "candidate_id": <int> }

POST /interview/respond
    Submit the candidate's answer and receive the next question.
    Body: { "session_id": <int>, "answer": "<text>" }

GET  /interview/history/{session_id}
    Retrieve the full Q&A history for a session.

GET  /interview/sessions
    List all interview sessions (with optional candidate_id filter).
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.tables import InterviewSession
from agents.interview_agent.agent import interview_agent
from agents.bias_detection_agent.agent import bias_detection_agent

logger = logging.getLogger("app.routes.interview")

router = APIRouter(prefix="/interview", tags=["Interview"])


# ── Request / Response Schemas ────────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    candidate_id: int = Field(..., description="ID of the candidate to interview.")


class RespondRequest(BaseModel):
    session_id: int = Field(..., description="The active interview session ID.")
    answer: str = Field(..., min_length=1, description="The candidate's answer to the last question.")
    candidate_id: int = Field(default=None, description="Candidate ID for authorization (required for candidates)")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/test", summary="Unified interview test console (text + voice)")
async def interview_test_page():
    """
    Serves interview_test.html over HTTP.
    Required for voice mode — Chrome blocks AudioWorklet when loaded via file://.
    Open: http://localhost:8000/interview/test
    """
    html_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "interview_test.html",
    )
    return FileResponse(html_path, media_type="text/html")


@router.post(
    "/start",
    summary="Start a new interview session",
    response_description="First interview question + session metadata",
)
async def start_interview(
    body: StartSessionRequest,
    db: Session = Depends(get_db),
):
    """
    Creates an `InterviewSession` record, generates the first tailored question
    based on the candidate's resume and screening result, and returns it.

    The candidate must have already been processed by the extraction agent
    (i.e. `extracted_resume_json` must be present in the candidates table).
    """
    logger.info(f"[Route] POST /interview/start — candidate_id={body.candidate_id}")
    result = interview_agent.start_session(candidate_id=body.candidate_id, db=db)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.post(
    "/respond",
    summary="Submit an answer and get the next question",
    response_description="Next interview question or completion message",
)
async def respond_to_interview(
    body: RespondRequest,
    db: Session = Depends(get_db),
):
    """
    Records the candidate's answer to the pending question, then either:
    - Returns the next AI-generated question (if < 10 questions asked), or
    - Returns a closing message and marks the session as `completed`.

    All Q&A turns are persisted to the `interview_chats` table with timestamps.
    
    Security: If candidate_id is provided, validates that the session belongs to that candidate.
    """
    logger.info(f"[Route] POST /interview/respond — session_id={body.session_id} | candidate_id={body.candidate_id} | answer_len={len(body.answer)}")
    
    # Authorization check: if candidate_id is provided, verify session ownership
    if body.candidate_id is not None:
        session = db.query(InterviewSession).filter(InterviewSession.id == body.session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found.")
        if session.candidate_id != body.candidate_id:
            raise HTTPException(
                status_code=403, 
                detail="Access denied. This session does not belong to you."
            )
    
    result = interview_agent.respond(session_id=body.session_id, answer=body.answer, db=db)

    if "error" in result:
        status_code = 404 if "not found" in result["error"].lower() else 400
        raise HTTPException(status_code=status_code, detail=result["error"])

    return result


@router.get(
    "/history/{session_id}",
    summary="Get full Q&A history for a session",
    response_description="List of all questions and answers with timestamps",
)
async def get_interview_history(
    session_id: int,
    candidate_id: int = Query(default=None, description="Candidate ID for authorization (required for candidates)"),
    db: Session = Depends(get_db),
):
    """
    Returns the complete chat history for the given session, including:
    - All questions asked, in order
    - The candidate's answers
    - Timestamps for each turn
    - Session metadata (status, start/end times, candidate info)
    
    Security: If candidate_id is provided, validates that the session belongs to that candidate.
    """
    logger.info(f"[Route] GET /interview/history/{session_id} | candidate_id={candidate_id}")
    
    # Authorization check: if candidate_id is provided, verify session ownership
    if candidate_id is not None:
        session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found.")
        if session.candidate_id != candidate_id:
            raise HTTPException(
                status_code=403, 
                detail="Access denied. This session does not belong to you."
            )
    
    result = interview_agent.get_history(session_id=session_id, db=db)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.get(
    "/sessions",
    summary="List all interview sessions",
    response_description="Paginated list of interview sessions",
)
async def list_sessions(
    candidate_id: int = Query(default=None, description="Filter by candidate ID"),
    status: str = Query(default=None, description="Filter by status: active | completed | aborted"),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0),
    db: Session = Depends(get_db),
):
    """
    Lists interview sessions. Optionally filter by candidate_id or status.
    Useful for dashboards and admin views.
    """
    query = db.query(InterviewSession)
    if candidate_id is not None:
        query = query.filter(InterviewSession.candidate_id == candidate_id)
    if status is not None:
        query = query.filter(InterviewSession.status == status)

    total = query.count()
    sessions = query.order_by(InterviewSession.started_at.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "sessions": [
            {
                "session_id": s.id,
                "candidate_id": s.candidate_id,
                "candidate_name": s.candidate_name,
                "status": s.status,
                "question_count": s.question_count,
                "max_questions": s.max_questions,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            }
            for s in sessions
        ],
    }


@router.get(
    "/candidates",
    summary="List all candidates and their statuses",
    response_description="Array of candidates with screening and interview status",
)
async def list_candidates(db: Session = Depends(get_db)):
    """
    Returns all candidates, including their screening score, rejection status,
    and interview status. Also attaches the evaluation visualisation data if completed.
    """
    from app.models.tables import Candidate
    candidates = db.query(Candidate).order_by(Candidate.id.desc()).all()
    results = []
    
    for c in candidates:
        # Determine base screening status
        status = "Pending"
        score = None
        if c.screening_result:
            score = c.screening_result.get("scores", {}).get("overall_fit")
            if score is not None and score < 90:
                status = "Rejected"
            elif score is not None:
                status = "Shortlisted"
        
        # Check interview sessions if shortlisted
        report_path = None
        eval_result = c.bias_flags
        if status == "Shortlisted":
            session = db.query(InterviewSession).filter(InterviewSession.candidate_id == c.id).order_by(InterviewSession.id.desc()).first()
            if session:
                status = session.status.capitalize()
                if session.report_path:
                    report_path = session.report_path
                if session.evaluation_result:
                    eval_result = session.evaluation_result
        
        results.append({
            "id": c.id,
            "name": c.name or "Unknown",
            "email": c.email or "N/A",
            "score": score,
            "status": status,
            "eval_result": eval_result,
            "report_path": report_path
        })
        
    return results

@router.post(
    "/analyze/{session_id}",
    summary="Run bias & performance analysis on a completed interview session",
    response_description="Full analysis with bot metrics, candidate metrics, bias flags, and recommendations",
)
async def analyze_interview(
    session_id: int,
    db: Session = Depends(get_db),
):
    """
    Runs the BiasDetectionAgent on the given session and returns a detailed report:

    **Bot Metrics (5 scores 0–100):**
    - `question_quality_score` — clarity, structure, relevance of questions asked
    - `bias_risk_score`        — protected characteristics / illegal questions (lower = better)
    - `adaptability_score`     — how well questions adapted to candidate's answers
    - `topic_coverage_score`   — coverage of key competency areas from JD/resume
    - `consistency_score`      — uniform depth, tone, and challenge level

    **Candidate Metrics (5 scores 0–100):**
    - `communication_clarity_score`   — articulation, structure, coherence
    - `relevance_score`               — staying on-topic, penalised for skips
    - `technical_competency_score`    — demonstrated skills vs. role requirements
    - `confidence_conviction_score`   — assertive language, ownership of achievements
    - `engagement_depth_score`        — answer depth, curiosity, post-interview questions

    Results are **automatically saved** to the candidate's `bias_flags` column in the database.

    The session must be in `completed` or `post_interview` status.
    """
    logger.info(f"[Route] POST /interview/analyze/{session_id}")
    result = bias_detection_agent.analyze(session_id=session_id, db=db)

    if "error" in result:
        status_code = 404 if "not found" in result["error"].lower() else 400
        raise HTTPException(status_code=status_code, detail=result["error"])

    return result


@router.get(
    "/analysis/{candidate_id}",
    summary="Retrieve saved bias & performance analysis for a candidate",
    response_description="Last saved analysis report from the candidate's database record",
)
async def get_analysis(
    candidate_id: int,
    db: Session = Depends(get_db),
):
    """
    Returns the most recently saved bias analysis for the given candidate.
    The analysis is stored in the `bias_flags` JSON column of the candidates table.

    Run `POST /interview/analyze/{session_id}` first to generate the report.
    """
    logger.info(f"[Route] GET /interview/analysis/{candidate_id}")
    result = bias_detection_agent.get_analysis(candidate_id=candidate_id, db=db)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.post(
    "/report/{session_id}",
    summary="Generate final evaluation report and email to HR",
)
async def generate_report(
    session_id: int,
    db: Session = Depends(get_db),
):
    """
    Manually trigger the Final Report Agent for a session.

    Requires:
    - Session must be completed
    - BiasDetectionAgent must have already run (evaluation_result must be present)

    The report is:
    1. Generated as a .docx Word document
    2. Saved to the reports/ directory
    3. Emailed to HR with the document attached

    This runs synchronously (returns when done). Use the background trigger
    if you want fire-and-forget behaviour.
    """
    from agents.final_report_agent.agent import final_report_agent
    logger.info(f"[Route] POST /interview/report/{session_id}")
    result = final_report_agent.generate(session_id=session_id, db=db)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.get(
    "/report/{session_id}/download",
    summary="Download the generated .docx report for a session",
)
async def download_report(
    session_id: int,
    db: Session = Depends(get_db),
):
    """Download the already-generated Word report for a session."""
    from fastapi.responses import FileResponse
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found.")
    if not session.report_path:
        raise HTTPException(
            status_code=404,
            detail="Report not yet generated. POST /interview/report/{session_id} first.",
        )
    if not os.path.exists(session.report_path):
        raise HTTPException(status_code=404, detail="Report file not found on disk.")

    return FileResponse(
        path=session.report_path,
        filename=os.path.basename(session.report_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
