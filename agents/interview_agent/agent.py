"""
Interview Agent
===============
Standalone AI agent that conducts a structured screening interview.

Session lifecycle (status field):
  greeting      → Bot greeted, waiting for candidate to respond
  active        → Interview questions in progress (up to max_questions)
  post_interview → All questions done; candidate can ask HR questions
  completed     → Session fully closed

Public API
----------
  start_session(candidate_id, db) -> dict
  respond(session_id, answer, db) -> dict
  get_history(session_id, db) -> dict
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from google import genai
from sqlalchemy.orm import Session

from agents.interview_agent.prompts import (
    CLOSING_MESSAGE,
    GREETING_MESSAGE,
    OPENING_QUESTION_PROMPT,
    POST_INTERVIEW_GREETING,
    POST_INTERVIEW_SMART_PROMPT,
    SMART_ACTIVE_PROMPT,
)
from app.models.tables import Candidate, InterviewChat, InterviewSession

load_dotenv()
logger = logging.getLogger("agents.interview_agent")


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


class InterviewAgent:
    MODEL_NAME = "gemini-2.5-flash"
    MAX_QUESTIONS = 10

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("[InterviewAgent] GEMINI_API_KEY is not set.")
        self.client = genai.Client(api_key=self.api_key)
        logger.info(f"[{_ts()}] InterviewAgent ready — model: {self.MODEL_NAME}")

    # ──────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _fetch_candidate(self, candidate_id: int, db: Session) -> Candidate | None:
        return db.query(Candidate).filter(Candidate.id == candidate_id).first()

    def _call_llm(self, prompt: str) -> str:
        """Call Gemini and return plain text."""
        t0 = time.perf_counter()
        response = self.client.models.generate_content(
            model=self.MODEL_NAME,
            contents=prompt,
        )
        logger.info(f"[{_ts()}] 🤖 LLM {time.perf_counter()-t0:.2f}s")
        return response.text.strip()

    def _call_llm_json(self, prompt: str) -> dict:
        """Call Gemini expecting JSON back. Falls back gracefully on parse errors."""
        from google.genai import types
        t0 = time.perf_counter()
        try:
            response = self.client.models.generate_content(
                model=self.MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            logger.info(f"[{_ts()}] 🤖 LLM-JSON {time.perf_counter()-t0:.2f}s")
            return json.loads(response.text.strip())
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning(f"[{_ts()}] ⚠ JSON parse fallback: {exc}")
            # Return a safe default so the flow doesn't break
            return {"action": "next_question", "response": response.text.strip() if 'response' in dir() else "Could you elaborate on that?"}

    def _build_history_text(self, session_id: int, db: Session) -> str:
        chats = (
            db.query(InterviewChat)
            .filter(
                InterviewChat.session_id == session_id,
                InterviewChat.question_number <= self.MAX_QUESTIONS,
            )
            .order_by(InterviewChat.question_number)
            .all()
        )
        lines = []
        for c in chats:
            lines.append(f"Q{c.question_number}: {c.question}")
            if c.answer:
                lines.append(f"A{c.question_number}: {c.answer}")
        return "\n".join(lines) if lines else "(no conversation yet)"

    def _get_last_unanswered(self, session_id: int, db: Session) -> InterviewChat | None:
        return (
            db.query(InterviewChat)
            .filter(
                InterviewChat.session_id == session_id,
                InterviewChat.answer == None,  # noqa: E711
                InterviewChat.question_number <= self.MAX_QUESTIONS,
            )
            .order_by(InterviewChat.question_number.desc())
            .first()
        )

    def _save_interview_question(
        self, session: InterviewSession, q_num: int, q_text: str, db: Session
    ) -> InterviewChat:
        chat = InterviewChat(
            session_id=session.id,
            candidate_name=session.candidate_name,
            question_number=q_num,
            question=q_text,
            answer=None,
        )
        db.add(chat)
        db.flush()
        return chat

    def _save_post_interview_turn(
        self, session: InterviewSession, user_msg: str, bot_reply: str, db: Session
    ):
        """Save post-interview Q&A turns with question_number > MAX_QUESTIONS."""
        existing = (
            db.query(InterviewChat)
            .filter(
                InterviewChat.session_id == session.id,
                InterviewChat.question_number > self.MAX_QUESTIONS,
            )
            .count()
        )
        turn_num = self.MAX_QUESTIONS + existing + 1
        chat = InterviewChat(
            session_id=session.id,
            candidate_name=session.candidate_name,
            question_number=turn_num,
            question=user_msg,   # user's HR question
            answer=bot_reply,    # bot's HR answer
            timestamp=datetime.now(timezone.utc),
        )
        db.add(chat)

    def _trigger_bias_analysis_background(self, session_id: int) -> None:
        """
        Spawn a daemon thread to run bias analysis after session completion.
        Uses its own DB session so it doesn't conflict with the request session.
        The main response is returned to the user immediately — no blocking.
        """
        def _run():
            try:
                # Lazy import inside thread to avoid circular imports at module load time
                from agents.bias_detection_agent.agent import bias_detection_agent
                from app.database import SessionLocal

                db = SessionLocal()
                try:
                    logger.info(
                        f"[{_ts()}] 🔍 [BG] Bias analysis starting — session={session_id}"
                    )
                    result = bias_detection_agent.analyze(session_id=session_id, db=db)
                    if "error" in result:
                        logger.warning(
                            f"[{_ts()}] ⚠ [BG] Bias analysis error: {result['error']}"
                        )
                    else:
                        bot_score = result.get("bot_metrics", {}).get("overall_score", "N/A")
                        cand_score = result.get("candidate_metrics", {}).get("overall_score", "N/A")
                        logger.info(
                            f"[{_ts()}] ✅ [BG] Bias analysis saved — "
                            f"session={session_id} | "
                            f"bot={bot_score} | candidate={cand_score}"
                        )
                finally:
                    db.close()
            except Exception as exc:
                logger.error(
                    f"[{_ts()}] ❌ [BG] Bias analysis failed — session={session_id}: {exc}",
                    exc_info=True,
                )

        thread = threading.Thread(target=_run, daemon=True, name=f"bias-{session_id}")
        thread.start()
        logger.info(f"[{_ts()}] 🚀 Bias analysis thread launched — session={session_id}")

    # ──────────────────────────────────────────────────────────────────────────
    # Phase handlers
    # ──────────────────────────────────────────────────────────────────────────

    def _handle_greeting_response(
        self, session: InterviewSession, user_msg: str, db: Session
    ) -> dict:
        """
        Any response during greeting phase is treated as 'I'm ready'.
        Generate Q1 and transition to active.
        """
        logger.info(f"[{_ts()}] 👋 Greeting response received — generating Q1")

        candidate = self._fetch_candidate(session.candidate_id, db)
        resume_json = (candidate.extracted_resume_json or {}) if candidate else {}
        screening_json = (candidate.screening_result or {}) if candidate else {}

        prompt = OPENING_QUESTION_PROMPT.format(
            resume_json=json.dumps(resume_json, indent=2),
            screening_json=json.dumps(screening_json, indent=2),
        )
        q1 = self._call_llm(prompt)

        self._save_interview_question(session, 1, q1, db)
        session.question_count = 1
        session.status = "active"
        db.commit()

        logger.info(f"[{_ts()}] ✅ Q1 generated — session {session.id} now active")

        return {
            "session_id": session.id,
            "candidate_name": session.candidate_name,
            "status": "active",
            "bot_message": f"Great! Let's get started. 🎯\n\n{q1}",
            "question_number": 1,
            "is_interview_question": True,
            "questions_remaining": self.MAX_QUESTIONS - 1,
            "message": f"Question 1 of {self.MAX_QUESTIONS}.",
        }

    def _handle_active_response(
        self, session: InterviewSession, user_msg: str, db: Session
    ) -> dict:
        """
        During interview:
        - If answer is relevant → save + next question (or transition to post_interview)
        - If irrelevant → redirect back to pending question
        """
        last_chat = self._get_last_unanswered(session.id, db)
        if not last_chat:
            logger.warning(f"[{_ts()}] No pending question found for session {session.id}")
            return {"error": "No pending question found. Something went wrong."}

        candidate = self._fetch_candidate(session.candidate_id, db)
        resume_json = (candidate.extracted_resume_json or {}) if candidate else {}
        screening_json = (candidate.screening_result or {}) if candidate else {}
        history = self._build_history_text(session.id, db)

        prompt = SMART_ACTIVE_PROMPT.format(
            current_question=last_chat.question,
            user_answer=user_msg,
            resume_json=json.dumps(resume_json, indent=2),
            screening_json=json.dumps(screening_json, indent=2),
            history=history,
            questions_asked=session.question_count,
            max_questions=session.max_questions,
        )
        result = self._call_llm_json(prompt)
        action = result.get("action", "next_question")
        response_text = result.get("response", "")

        # ── IRRELEVANT → redirect ──────────────────────────────────────────────
        if action == "redirect":
            logger.info(f"[{_ts()}] 🔄 Redirect sent — Q{last_chat.question_number} still pending")
            db.commit()
            return {
                "session_id": session.id,
                "candidate_name": session.candidate_name,
                "status": "active",
                "bot_message": response_text,
                "question_number": last_chat.question_number,
                "is_interview_question": False,
                "is_redirect": True,
                "questions_remaining": self.MAX_QUESTIONS - session.question_count,
                "message": f"Please answer question {last_chat.question_number}.",
            }

        # ── SKIP → mark skipped, move forward ────────────────────────────────
        if action == "skip":
            last_chat.answer = "[Skipped by candidate]"
            last_chat.timestamp = datetime.now(timezone.utc)
            logger.info(f"[{_ts()}] ⏭ Q{last_chat.question_number} skipped")
            # The LLM already embedded the next question in `response_text`
            # so we treat the rest exactly like next_question
            action = "next_question"
            was_skipped = True
        else:
            was_skipped = False

        # ── RELEVANT → save answer ────────────────────────────────────────────
        # Only overwrite answer if this was a genuine answer, not a skip
        if not was_skipped:
            last_chat.answer = user_msg.strip()
            last_chat.timestamp = datetime.now(timezone.utc)
        logger.info(f"[{_ts()}] 💬 Answer saved — Q{last_chat.question_number}")

        # Transition to post_interview if all questions answered
        if session.question_count >= session.max_questions:
            session.status = "post_interview"
            db.commit()
            logger.info(f"[{_ts()}] 🏁 All {session.max_questions} Qs done — post_interview phase")
            closing_q = POST_INTERVIEW_GREETING.format(max_questions=session.max_questions)
            return {
                "session_id": session.id,
                "candidate_name": session.candidate_name,
                "status": "post_interview",
                "bot_message": closing_q,
                "question_number": session.question_count,
                "is_interview_question": False,
                "questions_remaining": 0,
                "message": "Interview complete. Candidate may now ask questions.",
            }

        # Generate next interview question
        next_q_num = session.question_count + 1
        self._save_interview_question(session, next_q_num, response_text, db)
        session.question_count = next_q_num
        db.commit()

        questions_remaining = session.max_questions - next_q_num
        is_last = questions_remaining == 0
        logger.info(f"[{_ts()}] ✅ Q{next_q_num} generated | remaining={questions_remaining}")

        return {
            "session_id": session.id,
            "candidate_name": session.candidate_name,
            "status": "active",
            "bot_message": response_text,
            "question_number": next_q_num,
            "is_interview_question": True,
            "questions_remaining": questions_remaining,
            "message": (
                f"Question {next_q_num} of {session.max_questions}."
                + (" (Last question!)" if is_last else "")
            ),
        }

    def _handle_post_interview_response(
        self, session: InterviewSession, user_msg: str, db: Session
    ) -> dict:
        """
        After all questions: answer HR questions or gracefully close the session.
        """
        candidate = self._fetch_candidate(session.candidate_id, db)
        resume_json = (candidate.extracted_resume_json or {}) if candidate else {}

        prompt = POST_INTERVIEW_SMART_PROMPT.format(
            message=user_msg,
            resume_json=json.dumps(resume_json, indent=2),
        )
        result = self._call_llm_json(prompt)
        action = result.get("action", "answer")
        response_text = result.get("response", "")

        if action == "close":
            # Save the closing exchange then mark completed
            self._save_post_interview_turn(session, user_msg, response_text, db)
            session.status = "completed"
            session.ended_at = datetime.now(timezone.utc)
            db.commit()
            logger.info(f"[{_ts()}] 🔒 Session {session.id} completed")

            # Fire-and-forget: bias analysis runs in background, doesn't block response
            self._trigger_bias_analysis_background(session.id)

            return {
                "session_id": session.id,
                "candidate_name": session.candidate_name,
                "status": "completed",
                "bot_message": response_text,
                "question_number": session.question_count,
                "is_interview_question": False,
                "questions_remaining": 0,
                "message": "Session closed.",
            }

        # action == "answer" — save HR Q&A turn
        self._save_post_interview_turn(session, user_msg, response_text, db)
        db.commit()
        logger.info(f"[{_ts()}] 💼 HR answer sent | session={session.id}")
        return {
            "session_id": session.id,
            "candidate_name": session.candidate_name,
            "status": "post_interview",
            "bot_message": response_text,
            "question_number": session.question_count,
            "is_interview_question": False,
            "questions_remaining": 0,
            "message": "Candidate Q&A in progress.",
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def start_session(self, candidate_id: int, db: Session) -> dict:
        """
        Start a new interview session.
        Returns a greeting message — does NOT ask Q1 yet.
        The interview starts only after the candidate responds.
        """
        logger.info(f"[{_ts()}] ── START SESSION | candidate_id={candidate_id}")

        candidate = self._fetch_candidate(candidate_id, db)
        if not candidate:
            return {"error": f"Candidate with id={candidate_id} not found."}

        session = InterviewSession(
            candidate_id=candidate_id,
            candidate_name=candidate.name,
            status="greeting",
            question_count=0,
            max_questions=self.MAX_QUESTIONS,
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        name_part = f" {candidate.name.split()[0]}" if candidate.name else ""
        greeting = GREETING_MESSAGE.format(name_part=name_part)

        logger.info(f"[{_ts()}] ✅ Session {session.id} created — status: greeting")

        return {
            "session_id": session.id,
            "candidate_id": candidate_id,
            "candidate_name": candidate.name,
            "status": "greeting",
            "bot_message": greeting,
            "question_number": 0,
            "is_interview_question": False,
            "questions_remaining": self.MAX_QUESTIONS,
            "message": "Session started. Waiting for candidate to respond.",
        }

    def respond(self, session_id: int, answer: str, db: Session) -> dict:
        """
        Process a candidate's message and return the next bot response.
        Routes to the correct phase handler based on session.status.
        """
        session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
        if not session:
            return {"error": f"Session {session_id} not found."}

        if session.status == "completed":
            return {
                "error": "This session is already completed. Please start a new session.",
                "status": "completed",
            }

        answer = answer.strip()
        logger.info(
            f"[{_ts()}] ── RESPOND | session={session_id} | "
            f"status={session.status} | answer_len={len(answer)}"
        )

        if session.status == "greeting":
            return self._handle_greeting_response(session, answer, db)
        elif session.status == "active":
            return self._handle_active_response(session, answer, db)
        elif session.status == "post_interview":
            return self._handle_post_interview_response(session, answer, db)

        return {"error": f"Unknown session status: '{session.status}'"}

    def get_history(self, session_id: int, db: Session) -> dict:
        """Full Q&A history for a session."""
        session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
        if not session:
            return {"error": f"Session {session_id} not found."}

        chats = (
            db.query(InterviewChat)
            .filter(InterviewChat.session_id == session_id)
            .order_by(InterviewChat.question_number)
            .all()
        )

        interview_history = []
        hr_qna = []

        for c in chats:
            entry = {
                "question_number": c.question_number,
                "question": c.question,
                "answer": c.answer,
                "timestamp": c.timestamp.isoformat() if c.timestamp else None,
            }
            if c.question_number <= session.max_questions:
                interview_history.append(entry)
            else:
                hr_qna.append(entry)

        return {
            "session_id": session_id,
            "candidate_id": session.candidate_id,
            "candidate_name": session.candidate_name,
            "status": session.status,
            "question_count": session.question_count,
            "max_questions": session.max_questions,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            "interview_history": interview_history,
            "post_interview_qna": hr_qna,
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
interview_agent = InterviewAgent()
