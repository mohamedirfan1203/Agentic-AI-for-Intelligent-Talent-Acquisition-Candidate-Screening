"""
Bias Detection Agent
====================
Standalone agent that evaluates a completed interview session and produces:

  Bot Metrics (5):
    1. question_quality_score      — clarity, relevance, structure
    2. bias_risk_score             — protected characteristics, illegal questions (lower = better)
    3. adaptability_score          — personalisation based on candidate answers
    4. topic_coverage_score        — completeness of competency coverage
    5. consistency_score           — uniform depth, tone, and challenge

  Candidate Metrics (5):
    1. communication_clarity_score — articulation and structure
    2. relevance_score             — on-topic, no skips
    3. technical_competency_score  — demonstrated job-relevant skills
    4. confidence_conviction_score — assertiveness, ownership language
    5. engagement_depth_score      — thoroughness, post-interview curiosity

Results are saved to:
  - Candidate.bias_flags  (JSON column) — full analysis report
  - InterviewSession      — bias_analyzed flag (not added to schema, tracked via bias_flags presence)

Public API
----------
  BiasDetectionAgent.analyze(session_id, db) -> dict
"""

import json
import logging
import os
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from google import genai
from google.genai import types
from sqlalchemy.orm import Session

from agents.bias_detection_agent.prompts import BIAS_ANALYSIS_PROMPT
from app.models.tables import Candidate, InterviewChat, InterviewSession

load_dotenv()
logger = logging.getLogger("agents.bias_detection_agent")


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


class BiasDetectionAgent:
    """
    Standalone bias & performance audit agent.
    Completely independent of the orchestrator and interview agent.
    """

    MODEL_NAME = "gemini-2.5-flash"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("[BiasDetectionAgent] GEMINI_API_KEY is not set.")
        self.client = genai.Client(api_key=self.api_key)
        logger.info(f"[{_ts()}] BiasDetectionAgent ready — model: {self.MODEL_NAME}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_transcript(self, chats: list[InterviewChat]) -> str:
        """Format the full interview Q&A into a readable transcript."""
        lines = []
        for c in chats:
            if c.question_number <= 10:
                label = f"Q{c.question_number} [Bot]"
            else:
                label = f"Post-Interview Q{c.question_number - 10} [Candidate→HR]"

            lines.append(f"{label}: {c.question}")

            if c.answer:
                answer_label = (
                    "HR [Bot]" if c.question_number > 10 else f"A{c.question_number} [Candidate]"
                )
                lines.append(f"{answer_label}: {c.answer}")
            else:
                lines.append(f"A{c.question_number} [Candidate]: (no answer)")
            lines.append("")  # blank line between turns

        return "\n".join(lines).strip()

    def _count_skips(self, chats: list[InterviewChat]) -> int:
        return sum(
            1 for c in chats
            if c.answer == "[Skipped by candidate]" and c.question_number <= 10
        )

    def _count_post_interview_user_questions(self, chats: list[InterviewChat]) -> int:
        return sum(1 for c in chats if c.question_number > 10)

    def _call_llm(self, prompt: str) -> dict:
        """Call Gemini with JSON mode and return parsed dict."""
        t0 = time.perf_counter()
        response = self.client.models.generate_content(
            model=self.MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        latency = time.perf_counter() - t0
        usage = getattr(response, "usage_metadata", None)
        token_info = (
            f"tokens: {usage.prompt_token_count}→{usage.candidates_token_count}"
            if usage else "tokens: N/A"
        )
        logger.info(f"[{_ts()}] 🤖 LLM responded in {latency:.2f}s | {token_info}")
        return json.loads(response.text.strip())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, session_id: int, db: Session) -> dict:
        """
        Run the full bias & performance analysis on a completed interview session.

        Steps:
          1. Load session + all chat turns from DB
          2. Load candidate record (resume + screening data)
          3. Build structured transcript
          4. Call Gemini with the comprehensive audit prompt
          5. Save full result to Candidate.bias_flags
          6. Return the analysis dict

        Args:
            session_id: ID of the InterviewSession to analyse
            db:         SQLAlchemy session

        Returns:
            Full analysis dict including bot_metrics, candidate_metrics,
            bias_flags, recommendations, overall_analysis, and metadata.
        """
        t0 = time.perf_counter()
        logger.info(f"[{_ts()}] ── BiasDetectionAgent START | session_id={session_id}")

        # ── Step 1: Load session ──────────────────────────────────────────────
        session: InterviewSession = (
            db.query(InterviewSession)
            .filter(InterviewSession.id == session_id)
            .first()
        )
        if not session:
            return {"error": f"Session {session_id} not found."}

        if session.status not in ("completed", "post_interview"):
            return {
                "error": (
                    f"Session is '{session.status}'. "
                    "Analysis can only run on completed or post_interview sessions."
                ),
                "session_status": session.status,
            }

        # ── Step 2: Load all chat turns ───────────────────────────────────────
        chats: list[InterviewChat] = (
            db.query(InterviewChat)
            .filter(InterviewChat.session_id == session_id)
            .order_by(InterviewChat.question_number)
            .all()
        )
        if not chats:
            return {"error": "No interview messages found for this session."}

        # ── Step 3: Load candidate ────────────────────────────────────────────
        candidate: Candidate = (
            db.query(Candidate)
            .filter(Candidate.id == session.candidate_id)
            .first()
        )
        if not candidate:
            return {"error": f"Candidate {session.candidate_id} not found in database."}

        resume_json = candidate.extracted_resume_json or {}
        screening_json = candidate.screening_result or {}

        # ── Step 4: Build inputs ──────────────────────────────────────────────
        transcript = self._build_transcript(chats)
        skipped_count = self._count_skips(chats)
        post_q_count = self._count_post_interview_user_questions(chats)
        total_interview_qs = sum(1 for c in chats if c.question_number <= session.max_questions)

        logger.info(
            f"[{_ts()}] 📋 Session stats | "
            f"total_qs={total_interview_qs} | skips={skipped_count} | "
            f"post_interview_qs={post_q_count} | status={session.status}"
        )

        prompt = BIAS_ANALYSIS_PROMPT.format(
            resume_json=json.dumps(resume_json, indent=2),
            screening_json=json.dumps(screening_json, indent=2),
            transcript=transcript,
            total_questions=total_interview_qs,
            skipped_count=skipped_count,
            post_interview_questions=post_q_count,
            session_status=session.status,
        )

        # ── Step 5: Call Gemini ───────────────────────────────────────────────
        logger.info(f"[{_ts()}] 🤖 Calling Gemini ({self.MODEL_NAME}) — ~{len(prompt)//4:,} tokens")
        try:
            analysis = self._call_llm(prompt)
        except json.JSONDecodeError as exc:
            logger.error(f"[{_ts()}] ❌ JSON decode error: {exc}")
            return {"error": "LLM returned invalid JSON.", "details": str(exc)}
        except Exception as exc:
            logger.error(f"[{_ts()}] ❌ LLM call failed: {exc}")
            return {"error": "Analysis failed.", "details": str(exc)}

        # ── Step 6: Enrich with metadata ──────────────────────────────────────
        analysis["session_id"] = session_id
        analysis["candidate_id"] = session.candidate_id
        analysis["candidate_name"] = session.candidate_name
        analysis["analyzed_at"] = datetime.now(timezone.utc).isoformat()
        analysis["session_stats"] = {
            "total_questions": total_interview_qs,
            "skipped_count": skipped_count,
            "post_interview_questions_asked": post_q_count,
            "session_status": session.status,
        }

        # ── Step 7: Persist to Candidate.bias_flags + InterviewSession.evaluation_result ──
        candidate.bias_flags = analysis          # backward compat
        session.evaluation_result = analysis     # primary store for report agent
        db.commit()

        elapsed = time.perf_counter() - t0
        bot_score = analysis.get("bot_metrics", {}).get("overall_score", "N/A")
        cand_score = analysis.get("candidate_metrics", {}).get("overall_score", "N/A")
        bias_risk = analysis.get("bot_metrics", {}).get("bias_risk_score", "N/A")
        flag_count = len(analysis.get("bias_flags", []))

        logger.info(
            f"[{_ts()}] ✅ BiasDetectionAgent DONE | "
            f"bot_score={bot_score} | candidate_score={cand_score} | "
            f"bias_risk={bias_risk} | flags={flag_count} | {elapsed:.2f}s"
        )
        logger.info(f"[{_ts()}] 💾 Analysis saved → session_id={session_id}, candidate_id={candidate.id}")

        # ── Trigger final report generation (background) ──────────────────────
        # Import lazily to avoid circular imports
        try:
            from agents.final_report_agent.agent import final_report_agent
            final_report_agent.generate_in_background(session_id=session_id)
        except Exception as exc:
            logger.warning(f"[{_ts()}] ⚠ Could not launch report agent: {exc}")

        return analysis

    def get_analysis(self, candidate_id: int, db: Session) -> dict:
        """
        Retrieve the last saved bias analysis for a candidate from the DB.
        Returns the bias_flags JSON directly.
        """
        candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not candidate:
            return {"error": f"Candidate {candidate_id} not found."}
        if not candidate.bias_flags:
            return {"error": f"No bias analysis found for candidate {candidate_id}. Run /interview/analyze first."}
        return candidate.bias_flags


# ── Singleton ─────────────────────────────────────────────────────────────────
bias_detection_agent = BiasDetectionAgent()
