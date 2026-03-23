"""
Voice Interview Routes
=======================
REST + WebSocket endpoints for voice-based HR interviews.

These are completely independent of the text interview routes.

Endpoints
---------
POST /voice-interview/start
    Body: { "candidate_id": <int> }
    Creates an InterviewSession, returns session_id.
    The client must then open the WebSocket with ?session_id=<id>

WS   /voice-interview/ws?session_id=<int>
    Bidirectional proxy: Browser ↔ FastAPI ↔ Deepgram Voice Agent.
    Injects a personalised Deepgram Settings payload (with candidate's resume
    and screening data in the system prompt) so the LLM knows who it's talking to.
    Every ConversationText event is persisted to interview_chats in real-time.

GET  /voice-interview/history/{session_id}
    Returns the full Q&A transcript for a voice interview session
    (same format as text interview history).

GET  /voice-interview/sessions
    List / filter voice interview sessions.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from websockets.asyncio.client import connect as ws_connect

from app.database import SessionLocal, get_db
from app.models.tables import InterviewChat, InterviewSession
from agents.voice_agent.interview_agent import voice_interview_agent

logger = logging.getLogger("app.routes.voice_interview")

router = APIRouter(prefix="/voice-interview", tags=["Voice Interview"])


# ── Request schemas ───────────────────────────────────────────────────────────

class StartVoiceInterviewRequest(BaseModel):
    candidate_id: int = Field(..., description="ID of the candidate to interview.")


# ── REST endpoints ────────────────────────────────────────────────────────────

@router.post(
    "/start",
    summary="Start a new voice interview session",
)
async def start_voice_interview(
    body: StartVoiceInterviewRequest,
    db: Session = Depends(get_db),
):
    """
    Creates an InterviewSession record for the candidate.
    Returns:
    - session_id  → pass as ?session_id= when opening the WebSocket
    - candidate_name
    - websocket_url  → convenience hint for the client
    """
    logger.info(f"[Route] POST /voice-interview/start — candidate_id={body.candidate_id}")
    result = voice_interview_agent.start_session(
        candidate_id=body.candidate_id, db=db
    )

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return {
        "session_id": result["session_id"],
        "candidate_name": result["candidate_name"],
        "websocket_url": f"ws://localhost:8000/voice-interview/ws?session_id={result['session_id']}",
        "message": "Session created. Open the WebSocket URL to begin the voice interview.",
    }


@router.get(
    "/history/{session_id}",
    summary="Full Q&A transcript for a voice interview session",
)
async def get_voice_interview_history(
    session_id: int,
    db: Session = Depends(get_db),
):
    """Returns all saved turns for the session — same structure as text interview history."""
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found.")

    chats = (
        db.query(InterviewChat)
        .filter(InterviewChat.session_id == session_id)
        .order_by(InterviewChat.question_number)
        .all()
    )

    return {
        "session_id": session_id,
        "candidate_id": session.candidate_id,
        "candidate_name": session.candidate_name,
        "status": session.status,
        "question_count": session.question_count,
        "max_questions": session.max_questions,
        "mode": "voice",
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "transcript": [
            {
                "question_number": c.question_number,
                "bot": c.question,
                "candidate": c.answer,
                "timestamp": c.timestamp.isoformat() if c.timestamp else None,
            }
            for c in chats
        ],
    }


@router.get(
    "/sessions",
    summary="List voice interview sessions",
)
async def list_voice_interview_sessions(
    candidate_id: int = Query(default=None),
    status: str = Query(default=None),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0),
    db: Session = Depends(get_db),
):
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


# ── WebSocket proxy ───────────────────────────────────────────────────────────

@router.websocket("/ws")
async def voice_interview_websocket(
    client_ws: WebSocket,
    session_id: int = Query(..., description="Interview session ID from /voice-interview/start"),
):
    """
    Bidirectional voice proxy for HR interviews.

    Flow:
    1. Client POSTs /voice-interview/start → gets session_id
    2. Client opens ws://host/voice-interview/ws?session_id=<id>
    3. Server loads the session's personalised Deepgram Settings payload
    4. Connects to Deepgram, runs the handshake (Welcome → Settings → SettingsApplied)
    5. Proxies audio in both directions
    6. Every ConversationText event → persisted to interview_chats in real-time
    7. On disconnect → session marked completed, bias analysis triggered
    """
    await client_ws.accept()
    print(f"[VoiceInterview] ✅ Browser connected — session_id={session_id}", flush=True)
    logger.info(f"[VoiceInterview] Browser connected — session_id={session_id}")

    # Open a fresh DB session for this WebSocket connection's lifetime
    db = SessionLocal()
    try:
        # Load the session and rebuild the settings payload
        session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
        if not session:
            await client_ws.send_text(f'{{"error": "Session {session_id} not found."}}')
            await client_ws.close(code=1008)
            return

        if session.status == "completed":
            await client_ws.send_text('{"error": "This session is already completed."}')
            await client_ws.close(code=1008)
            return

        # Rebuild the fully personalised settings payload for this candidate
        rebuild = voice_interview_agent.start_session.__func__  # access helper data
        # Re-derive settings from the stored session (candidate already in DB)
        from app.models.tables import Candidate
        import copy
        from agents.voice_agent.config import AGENT_SETTINGS
        from agents.voice_agent.interview_prompts import build_voice_interview_prompt
        from agents.voice_agent.agent import voice_agent

        candidate = db.query(Candidate).filter(Candidate.id == session.candidate_id).first()
        resume_json = json.dumps(candidate.extracted_resume_json or {}, indent=2)
        screening_json = json.dumps(candidate.screening_result or {}, indent=2)

        system_prompt = build_voice_interview_prompt(
            candidate_name=candidate.name or "Candidate",
            resume_json=resume_json,
            screening_json=screening_json,
        )
        settings = copy.deepcopy(AGENT_SETTINGS)
        settings["agent"]["think"]["prompt"] = system_prompt
        settings["agent"]["greeting"] = (
            f"Hello {(candidate.name or 'there').split()[0]}! "
            "Welcome to your HR screening interview. "
            "I am your AI interviewer today. Are you ready to begin?"
        )
        settings_payload = json.dumps(settings)

        # Deepgram connection details
        dg_url = voice_agent.get_deepgram_ws_url()
        dg_headers = voice_agent.build_headers()

    except Exception as exc:
        print(f"[VoiceInterview] ❌ Setup error: {exc}", flush=True)
        logger.error(f"[VoiceInterview] Setup error: {exc}")
        await client_ws.send_text(f'{{"error": "{exc}"}}')
        await client_ws.close(code=1011)
        db.close()
        return

    print(f"[VoiceInterview] 🔗 Connecting to Deepgram for session {session_id}", flush=True)

    try:
        async with ws_connect(
            dg_url,
            additional_headers=dg_headers,
            ping_interval=20,
            ping_timeout=30,
            open_timeout=10,
        ) as dg_ws:
            print(f"[VoiceInterview] ✅ Deepgram connected — session {session_id}", flush=True)

            # ── Handshake: receive Welcome ────────────────────────────────
            welcome_raw = await dg_ws.recv()
            print(f"[VoiceInterview] 📩 Welcome: {welcome_raw[:120]}", flush=True)
            await client_ws.send_text(welcome_raw)

            # ── Send personalised Settings ────────────────────────────────
            await dg_ws.send(settings_payload)
            print(f"[VoiceInterview] 📤 Personalised Settings sent", flush=True)

            # ── Gate: block audio until SettingsApplied ───────────────────
            audio_gate = asyncio.Event()

            # ── Task A: browser → Deepgram (mic PCM) ──────────────────────
            async def browser_to_deepgram():
                print("[VoiceInterview] 🔒 Waiting for SettingsApplied…", flush=True)
                await audio_gate.wait()
                print("[VoiceInterview] 🔓 Audio gate open — streaming mic to Deepgram", flush=True)
                chunks = 0
                try:
                    while True:
                        msg = await client_ws.receive()
                        if "bytes" in msg and msg["bytes"]:
                            await dg_ws.send(msg["bytes"])
                            chunks += 1
                            if chunks % 200 == 0:
                                print(f"[VoiceInterview] 🎙 Chunks: {chunks}", flush=True)
                        elif "text" in msg and msg["text"]:
                            await dg_ws.send(msg["text"])
                        else:
                            break
                except WebSocketDisconnect:
                    print("[VoiceInterview] Browser disconnected (mic task)", flush=True)
                except Exception as exc:
                    print(f"[VoiceInterview] browser→dg error: {exc}", flush=True)

            # ── Task B: Deepgram → browser (TTS + events) ─────────────────
            async def deepgram_to_browser():
                audio_chunks = 0
                try:
                    async for message in dg_ws:
                        if isinstance(message, bytes):
                            await client_ws.send_bytes(message)
                            audio_chunks += 1
                            if audio_chunks == 1:
                                print("[VoiceInterview] 🔊 First TTS audio chunk!", flush=True)
                        else:
                            # JSON event
                            print(f"[VoiceInterview] 📩 DG: {message[:300]}", flush=True)
                            logger.info(f"[VoiceInterview] DG event: {message[:300]}")
                            await client_ws.send_text(message)

                            try:
                                evt = json.loads(message)
                                evt_type = evt.get("type", "")

                                # Open audio gate when settings acknowledged
                                if evt_type == "SettingsApplied":
                                    print("[VoiceInterview] ✅ SettingsApplied — gate open!", flush=True)
                                    audio_gate.set()

                                # Persist transcript turns to DB
                                elif evt_type == "ConversationText":
                                    role = evt.get("role", "")
                                    text = evt.get("content", "").strip()
                                    if text:
                                        voice_interview_agent.save_turn(
                                            session_id=session_id,
                                            role=role,
                                            text=text,
                                            db=db,
                                        )
                                        print(
                                            f"[VoiceInterview] 💾 Saved [{role}]: {text[:80]}",
                                            flush=True,
                                        )

                            except Exception as parse_exc:
                                logger.warning(f"[VoiceInterview] Event parse error: {parse_exc}")

                except Exception as exc:
                    print(f"[VoiceInterview] dg→browser error: {exc}", flush=True)
                    logger.warning(f"[VoiceInterview] dg→browser error: {exc}")

            browser_task = asyncio.create_task(browser_to_deepgram())
            dg_task = asyncio.create_task(deepgram_to_browser())

            done, pending = await asyncio.wait(
                [browser_task, dg_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            print(f"[VoiceInterview] ⏹ Session {session_id} — tasks stopped", flush=True)

    except Exception as exc:
        print(f"[VoiceInterview] ❌ Deepgram error [{type(exc).__name__}]: {exc}", flush=True)
        logger.error(f"[VoiceInterview] Deepgram error: {exc}")
        try:
            await client_ws.send_text(f'{{"error": "{exc}"}}')
        except Exception:
            pass
    finally:
        # Mark session completed and trigger bias analysis
        try:
            voice_interview_agent.complete_session(session_id=session_id, db=db)
        except Exception as exc:
            logger.warning(f"[VoiceInterview] complete_session error: {exc}")

        db.close()

        try:
            await client_ws.close()
        except Exception:
            pass

        print(f"[VoiceInterview] 🔌 Session {session_id} closed", flush=True)
        logger.info(f"[VoiceInterview] Session {session_id} closed")
