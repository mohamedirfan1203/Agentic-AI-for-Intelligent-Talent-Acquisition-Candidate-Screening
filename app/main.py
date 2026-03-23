from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import upload, interview, voice_interview, auth, frontend
from app.database import engine, Base
from app.models import tables
import logging

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("app.main")

# ── DB Tables ────────────────────────────────────────────────────────────────
try:
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created / verified successfully")
except Exception as e:
    logger.error(f"Error creating DB tables: {str(e)}")

# ── FastAPI App ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="HR-Bot Agentic System",
    description=(
        "Intelligent Recruitment & Interviewing Agentic AI.\n\n"
        "Architecture:\n"
        "  • OrchestratorAgent — main coordinator\n"
        "  • ExtractionAgent   — resume & JD structured data extraction sub-agent"
    ),
    version="0.2.0",
)

# ── CORS ─────────────────────────────────────────────────────────────────────
# Allow all origins so the HTML test file (file://) and any frontend can talk
# to this API during development. Restrict in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(frontend.router)
app.include_router(upload.router)
app.include_router(interview.router)
app.include_router(voice_interview.router)


@app.get("/", tags=["Health"])
async def root():
    return {
        "status": "online",
        "message": "HR-Bot Agentic API is ready.",
        "endpoints": {
            "portal": "GET /portal — HR-Bot Web Portal (UI)",
            "auth": [
                "POST /auth/signup                — HR sign-up",
                "POST /auth/login                 — Login (HR + Candidate)",
                "POST /auth/generate-candidate    — Generate candidate credentials & email",
                "GET  /auth/me/{username}         — Get user profile",
            ],
            "upload": [
                "POST /upload/resume-and-jd       — extract + screen resume & JD together",
            ],
            "interview": [
                "POST /interview/start             — start interview session for a candidate",
                "POST /interview/respond           — submit answer, get next question",
                "GET  /interview/history/{id}      — full Q&A history for a session",
                "GET  /interview/sessions          — list / filter all sessions",
                "POST /interview/analyze/{id}      — manually trigger bias & performance analysis",
                "GET  /interview/analysis/{cand}   — fetch saved bias analysis for a candidate",
            ],
            "voice_interview": [
                "POST /voice-interview/start           — create voice interview session for a candidate",
                "WS   /voice-interview/ws?session_id=  — voice interview WebSocket proxy",
                "GET  /voice-interview/history/{id}    — full Q&A transcript for a session",
                "GET  /voice-interview/sessions        — list / filter voice interview sessions",
            ],
            "docs": "GET /docs  — Swagger UI (all endpoints with schemas)",
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
