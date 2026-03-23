"""
Voice Interview Agent
======================
Manages HR interview sessions conducted over Deepgram Voice Agent.

Responsibilities
----------------
1. start_session(candidate_id, db)
   - Validates the candidate exists and has extracted resume / screening data
   - Creates an InterviewSession record (status = "greeting")
   - Returns the Deepgram Settings payload customised with the candidate's
     profile injected into the LLM system prompt

2. save_turn(session_id, role, text, db)
   - Called by the WebSocket route every time a ConversationText event arrives
   - Persists bot questions and candidate answers to interview_chats
   - Mirrors the text interview agent's DB structure exactly

3. complete_session(session_id, db)
   - Marks the session completed, fires bias analysis in background

Architecture note
-----------------
The LLM driving the interview runs INSIDE Deepgram (via their Voice Agent API).
We do NOT call Gemini separately — Deepgram handles STT → LLM → TTS end-to-end.
Our server only:
  a) Injects a personalised system prompt into the Settings payload
  b) Listens to ConversationText WebSocket events and persists the transcript
"""

import json
import logging
import threading
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from agents.voice_agent.config import AGENT_SETTINGS
from agents.voice_agent.interview_prompts import build_voice_interview_prompt
from app.models.tables import Candidate, InterviewChat, InterviewSession

logger = logging.getLogger("agents.voice_interview_agent")

MAX_QUESTIONS = 10


class VoiceInterviewAgent:
    """
    Thin coordinator for voice-based interviews.
    All conversational intelligence lives in the Deepgram-hosted LLM.
    This class owns DB persistence and session bookkeeping.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_session(self, candidate_id: int, db: Session) -> dict:
        """
        Validate candidate, create InterviewSession, build personalised
        Deepgram Settings payload.

        Returns:
            {
                "session_id": int,
                "candidate_name": str,
                "settings_payload": str,   ← send this to Deepgram as TEXT frame
            }
        or {"error": "..."} on failure.
        """
        candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not candidate:
            return {"error": f"Candidate {candidate_id} not found."}

        resume_json = json.dumps(candidate.extracted_resume_json or {}, indent=2)
        screening_json = json.dumps(candidate.screening_result or {}, indent=2)

        # Build personalised system prompt
        system_prompt = build_voice_interview_prompt(
            candidate_name=candidate.name or "Candidate",
            resume_json=resume_json,
            screening_json=screening_json,
        )

        # Deep-copy the base settings and inject the personalised prompt
        import copy
        settings = copy.deepcopy(AGENT_SETTINGS)
        settings["agent"]["think"]["prompt"] = system_prompt
        settings["agent"]["greeting"] = (
            f"Hello {(candidate.name or 'there').split()[0]}! "
            "Welcome to your HR screening interview. "
            "I'm your AI interviewer today. Are you ready to begin?"
        )

        # Create the DB session record
        session = InterviewSession(
            candidate_id=candidate_id,
            candidate_name=candidate.name,
            status="greeting",
            question_count=0,
            max_questions=MAX_QUESTIONS,
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        logger.info(
            f"[VoiceInterview] Session {session.id} created — "
            f"candidate={candidate.name}"
        )

        return {
            "session_id": session.id,
            "candidate_name": candidate.name,
            "settings_payload": json.dumps(settings),   # TEXT frame for Deepgram
        }

    def save_turn(
        self,
        session_id: int,
        role: str,       # "assistant" or "user"
        text: str,
        db: Session,
    ) -> None:
        """
        Persist a ConversationText turn to interview_chats.

        Bot messages  → stored as `question`  (answer = None initially)
        User messages → stored as `answer` on the most-recent unanswered bot row.

        This mirrors the text interview agent's DB pattern exactly:
          InterviewChat(question=<bot_q>, answer=<candidate_answer>)
        """
        session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
        if not session or session.status == "completed":
            return

        if role == "assistant":
            # New bot turn → create a new InterviewChat row with answer=None
            q_num = session.question_count + 1
            chat = InterviewChat(
                session_id=session_id,
                candidate_name=session.candidate_name,
                question_number=q_num,
                question=text,
                answer=None,
            )
            db.add(chat)
            session.question_count = q_num

            # Update status: first bot message → active, after that stays active
            if session.status == "greeting":
                session.status = "active"

            db.commit()
            logger.info(
                f"[VoiceInterview] Session {session_id} — "
                f"Bot Q{q_num} saved ({len(text)} chars)"
            )

        elif role == "user":
            # Candidate answered — find most-recent unanswered bot row
            last_unanswered = (
                db.query(InterviewChat)
                .filter(
                    InterviewChat.session_id == session_id,
                    InterviewChat.answer == None,  # noqa: E711
                )
                .order_by(InterviewChat.question_number.desc())
                .first()
            )
            if last_unanswered:
                last_unanswered.answer = text
                last_unanswered.timestamp = datetime.now(timezone.utc)
                db.commit()
                logger.info(
                    f"[VoiceInterview] Session {session_id} — "
                    f"User answer saved on Q{last_unanswered.question_number}"
                )
            else:
                # No pending question yet (e.g. candidate spoke during greeting)
                # Store as a standalone user turn
                chat = InterviewChat(
                    session_id=session_id,
                    candidate_name=session.candidate_name,
                    question_number=0,
                    question="[candidate spoke before first question]",
                    answer=text,
                    timestamp=datetime.now(timezone.utc),
                )
                db.add(chat)
                db.commit()

    def complete_session(self, session_id: int, db: Session) -> None:
        """
        Mark the session completed and fire bias analysis in the background.
        Called when the WebSocket connection closes.
        """
        session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
        if not session or session.status == "completed":
            return

        session.status = "completed"
        session.ended_at = datetime.now(timezone.utc)
        db.commit()
        logger.info(f"[VoiceInterview] Session {session_id} marked completed")

        self._trigger_bias_analysis_background(session_id)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _trigger_bias_analysis_background(self, session_id: int) -> None:
        def _run():
            try:
                from agents.bias_detection_agent.agent import bias_detection_agent
                from app.database import SessionLocal

                db = SessionLocal()
                try:
                    result = bias_detection_agent.analyze(session_id=session_id, db=db)
                    if "error" in result:
                        logger.warning(
                            f"[VoiceInterview][BG] Bias analysis error: {result['error']}"
                        )
                    else:
                        logger.info(
                            f"[VoiceInterview][BG] Bias analysis saved — session={session_id}"
                        )
                finally:
                    db.close()
            except Exception as exc:
                logger.error(
                    f"[VoiceInterview][BG] Bias analysis failed — session={session_id}: {exc}",
                    exc_info=True,
                )

        thread = threading.Thread(
            target=_run, daemon=True, name=f"voice-bias-{session_id}"
        )
        thread.start()
        logger.info(
            f"[VoiceInterview] Bias analysis thread launched — session={session_id}"
        )


# Singleton
voice_interview_agent = VoiceInterviewAgent()
