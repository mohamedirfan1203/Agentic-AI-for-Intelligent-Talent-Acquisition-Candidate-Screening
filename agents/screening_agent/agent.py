"""
Screening Agent
===============
Sub-agent that:
  1. Reads candidate_name + jd_doc_name from context (set by ExtractionAgent)
  2. Fetches candidate's extracted resume JSON from the Candidate table (by name)
  3. Fetches JD's extracted JSON from the JobDescription table (by doc_name)
  4. Sends both to Gemini for deep analysis
  5. Returns a structured matching scorecard

Interface: run(context: dict) -> dict
Context keys consumed:
  - candidate_name   (set by extraction agent)
  - jd_doc_name      (set by extraction agent)
  - db               (SQLAlchemy Session)
"""

import json
import logging
import os
import time
from datetime import datetime

from dotenv import load_dotenv
from google import genai
from google.genai import types
from sqlalchemy.orm import Session

from agents.screening_agent.prompts import SCREENING_PROMPT
from app.models.tables import Candidate, JobDescription

load_dotenv()

logger = logging.getLogger("agents.screening_agent")


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


class ScreeningAgent:
    """
    Screening sub-agent.
    Owns: DB lookups, LLM analysis, match score generation.
    """

    MODEL_NAME = "gemini-2.5-flash"
    DESCRIPTION = (
        "Analyses a candidate's resume against a job description and produces a detailed "
        "matching scorecard with per-dimension scores, skill gaps, strengths, and a "
        "hiring recommendation. Requires extraction to have run first so that both "
        "resume and JD data are available in the database."
    )

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("[ScreeningAgent] GEMINI_API_KEY is not set.")
        self.client = genai.Client(api_key=self.api_key)
        logger.info(f"[{_ts()}] ScreeningAgent ready — model: {self.MODEL_NAME}")

    # ------------------------------------------------------------------
    # Private: DB lookups
    # ------------------------------------------------------------------

    def _fetch_resume(self, candidate_name: str, db: Session) -> dict | None:
        """Fetch candidate's extracted resume JSON by name."""
        logger.info(f"[{_ts()}] 🔍 Fetching resume for candidate: '{candidate_name}'")
        candidate = (
            db.query(Candidate)
            .filter(Candidate.name.ilike(f"%{candidate_name}%"))
            .order_by(Candidate.created_at.desc())
            .first()
        )
        if not candidate:
            logger.warning(f"[{_ts()}] ⚠ No candidate found with name '{candidate_name}'")
            return None
        logger.info(f"[{_ts()}] ✅ Resume fetched — candidate_id={candidate.id}")
        return candidate.extracted_resume_json

    def _fetch_jd(self, jd_doc_name: str, db: Session) -> dict | None:
        """Fetch JD's extracted JSON by document name."""
        logger.info(f"[{_ts()}] 🔍 Fetching JD: '{jd_doc_name}'")
        jd = (
            db.query(JobDescription)
            .filter(JobDescription.doc_name == jd_doc_name)
            .order_by(JobDescription.created_at.desc())
            .first()
        )
        if not jd:
            logger.warning(f"[{_ts()}] ⚠ No JD found with doc_name '{jd_doc_name}'")
            return None
        logger.info(f"[{_ts()}] ✅ JD fetched — jd_id={jd.id}")
        return jd.extracted_json

    # ------------------------------------------------------------------
    # Public: run(context) — standard agent interface
    # ------------------------------------------------------------------

    def run(self, context: dict) -> dict:
        """
        Entry point called by the orchestrator.

        Reads from context:
          - candidate_name  → lookup resume in Candidate table
          - jd_doc_name     → lookup JD in JobDescription table
          - db              → SQLAlchemy session

        Returns:
          Structured scorecard dict with scores, gaps, strengths, recommendation.
        """
        t0 = time.perf_counter()
        db: Session = context.get("db")

        candidate_name: str = context.get("candidate_name")
        jd_doc_name: str = context.get("jd_doc_name")

        logger.info(
            f"[{_ts()}] ── ScreeningAgent START | "
            f"candidate='{candidate_name}' | jd='{jd_doc_name}'"
        )

        # Validate inputs
        if not candidate_name or not jd_doc_name:
            logger.error(
                f"[{_ts()}] ❌ Missing context keys — "
                f"candidate_name={candidate_name}, jd_doc_name={jd_doc_name}. "
                "Run extraction agent first."
            )
            return {
                "error": "candidate_name and jd_doc_name must be set in context. "
                         "Run extraction agent before screening."
            }

        # Step 1: Fetch data from DB
        resume_json = self._fetch_resume(candidate_name, db)
        jd_json = self._fetch_jd(jd_doc_name, db)

        if not resume_json:
            return {"error": f"Candidate '{candidate_name}' not found in database."}
        if not jd_json:
            return {"error": f"Job description '{jd_doc_name}' not found in database."}

        # Step 2: Call LLM for analysis
        prompt = SCREENING_PROMPT.format(
            resume_json=json.dumps(resume_json, indent=2),
            jd_json=json.dumps(jd_json, indent=2),
        )

        logger.info(
            f"[{_ts()}] 🤖 Calling Gemini ({self.MODEL_NAME}) — ~{len(prompt) // 4:,} tokens"
        )
        llm_start = time.perf_counter()
        try:
            response = self.client.models.generate_content(
                model=self.MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            llm_latency = time.perf_counter() - llm_start
            scorecard = json.loads(response.text)

            usage = getattr(response, "usage_metadata", None)
            token_info = (
                f"tokens: {usage.prompt_token_count}→{usage.candidates_token_count}"
                if usage else "tokens: N/A"
            )
            logger.info(
                f"[{_ts()}] ✅ Gemini responded in {llm_latency:.2f}s | {token_info}"
            )

        except json.JSONDecodeError as exc:
            logger.error(f"[{_ts()}] ❌ JSON decode error: {exc}")
            return {"error": "LLM returned invalid JSON", "details": str(exc)}
        except Exception as exc:
            logger.error(f"[{_ts()}] ❌ LLM call failed: {exc}")
            return {"error": "Screening analysis failed", "details": str(exc)}

        total = time.perf_counter() - t0
        overall = scorecard.get("scores", {}).get("overall_fit", "N/A")
        recommendation = scorecard.get("recommendation", "N/A")

        # Share scorecard with downstream agents (e.g. gmail_agent)
        context["screening_result"] = scorecard

        # Persist scorecard to Candidate table
        candidate = (
            db.query(Candidate)
            .filter(Candidate.name.ilike(f"%{candidate_name}%"))
            .order_by(Candidate.created_at.desc())
            .first()
        )
        if candidate:
            candidate.screening_result = scorecard
            db.commit()
            logger.info(
                f"[{_ts()}] 💾 Screening result saved → candidate_id={candidate.id}"
            )

        logger.info(
            f"[{_ts()}] ── ScreeningAgent DONE | "
            f"overall_fit={overall}/100 | recommendation='{recommendation}' | "
            f"total={total:.2f}s"
        )
        return scorecard


# Singleton
screening_agent = ScreeningAgent()
