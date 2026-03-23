"""
Extraction Agent
================
Sub-agent owns its full pipeline:
  1. Check DB cache first — if same filename was already extracted, return existing data
  2. Parse file to text (PDF/DOCX/TXT)
  3. Call Gemini LLM
  4. Persist to DB  (Candidate for resumes, JobDescription for JDs)
  5. Save intermediate JSON to disk
  6. Populate shared context keys for downstream agents

Interface: run(context: dict) -> dict
Context keys consumed:  resume_content/resume_filename, jd_content/jd_filename, db
Context keys produced:  candidate_id, candidate_name, jd_id, jd_doc_name
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Literal

from dotenv import load_dotenv
from google import genai
from google.genai import types
from sqlalchemy.orm import Session

from agents.extraction_agent.prompts import JD_EXTRACTION_PROMPT, RESUME_EXTRACTION_PROMPT
from agents.extraction_agent.tools import extract_text_from_file, save_extraction_result
from app.models.tables import Candidate, JobDescription

load_dotenv()

logger = logging.getLogger("agents.extraction_agent")
DocType = Literal["resume", "jd"]


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


class ExtractionAgent:
    """
    Extraction sub-agent.
    Owns: cache check, file parsing, LLM extraction, DB persistence, intermediate JSON save.
    """

    MODEL_NAME = "gemini-2.5-flash"
    DESCRIPTION = (
        "Extracts structured JSON data from resume and/or job description (JD) documents "
        "using Gemini LLM. Checks DB cache first — skips LLM if the same file was already "
        "extracted. Saves resume to Candidate table and JD to JobDescription table. "
        "Should run first whenever any document is uploaded."
    )

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("[ExtractionAgent] GEMINI_API_KEY is not set.")
        self.client = genai.Client(api_key=self.api_key)
        logger.info(f"[{_ts()}] ExtractionAgent ready — model: {self.MODEL_NAME}")

    # ------------------------------------------------------------------
    # Private: DB cache checks
    # ------------------------------------------------------------------

    def _check_resume_cache(self, filename: str, db: Session) -> dict | None:
        """Return cached result if this resume filename was already extracted."""
        existing = (
            db.query(Candidate)
            .filter(Candidate.source_filename == filename)
            .order_by(Candidate.created_at.desc())
            .first()
        )
        if existing:
            logger.info(
                f"[{_ts()}] ⚡ Cache HIT (resume) — '{filename}' already in DB "
                f"→ candidate_id={existing.id} | skipping LLM"
            )
            return {
                "candidate_id": existing.id,
                "candidate_name": existing.name,
                "extracted_data": existing.extracted_resume_json,
                "cache_hit": True,
            }
        logger.info(f"[{_ts()}] 🔍 Cache MISS (resume) — '{filename}' not found, will extract")
        return None

    def _check_jd_cache(self, filename: str, db: Session) -> dict | None:
        """Return cached result if this JD filename was already extracted."""
        existing = (
            db.query(JobDescription)
            .filter(JobDescription.doc_name == filename)
            .order_by(JobDescription.created_at.desc())
            .first()
        )
        if existing:
            logger.info(
                f"[{_ts()}] ⚡ Cache HIT (jd) — '{filename}' already in DB "
                f"→ jd_id={existing.id} | skipping LLM"
            )
            return {
                "jd_id": existing.id,
                "jd_doc_name": filename,
                "extracted_data": existing.extracted_json,
                "cache_hit": True,
            }
        logger.info(f"[{_ts()}] 🔍 Cache MISS (jd) — '{filename}' not found, will extract")
        return None

    # ------------------------------------------------------------------
    # Private: LLM extraction
    # ------------------------------------------------------------------

    def _extract(self, file_content: bytes, filename: str, doc_type: DocType) -> dict:
        """Parse file → call LLM → return structured dict."""
        t0 = time.perf_counter()
        logger.info(f"[{_ts()}] ── ExtractionAgent START [{doc_type.upper()}] {filename}")

        raw_text, parse_latency = extract_text_from_file(file_content, filename)
        if not raw_text:
            logger.error(f"[{_ts()}] ❌ No text extracted from '{filename}'")
            return {"error": "Could not extract text from file.", "filename": filename}

        prompt = (
            RESUME_EXTRACTION_PROMPT if doc_type == "resume" else JD_EXTRACTION_PROMPT
        ).format(raw_text=raw_text)

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
            extracted_data = json.loads(response.text)

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
            return {"error": "LLM extraction failed", "details": str(exc)}

        save_extraction_result(extracted_data, filename, doc_type)

        total = time.perf_counter() - t0
        logger.info(
            f"[{_ts()}] ── ExtractionAgent DONE [{doc_type.upper()}] "
            f"parse={parse_latency:.2f}s | llm={llm_latency:.2f}s | total={total:.2f}s"
        )
        return extracted_data

    # ------------------------------------------------------------------
    # Private: DB persistence
    # ------------------------------------------------------------------

    def _save_resume_to_db(self, extracted: dict, filename: str, db: Session, context: dict) -> dict:
        """Persist extracted resume → Candidate table. Populates context."""
        # Extract name - prioritize top-level 'name', fallback to 'full_name', then 'Unknown'
        candidate_name = extracted.get("name") or extracted.get("full_name", "Unknown")
        
        # Extract email - check top-level first, then nested contact_information
        candidate_email = extracted.get("email")
        if not candidate_email and isinstance(extracted.get("contact_information"), dict):
            candidate_email = extracted.get("contact_information", {}).get("email")
        
        candidate = Candidate(
            name=candidate_name,
            email=candidate_email,
            phone=extracted.get("phone"),
            source_filename=filename,
            extracted_resume_json=extracted,
        )
        db.add(candidate)
        db.commit()
        db.refresh(candidate)

        context["candidate_id"]   = candidate.id
        context["candidate_name"] = candidate.name

        logger.info(
            f"[{_ts()}] 💾 Candidate saved → id={candidate.id} | name='{candidate.name}'"
        )
        return {
            "candidate_id": candidate.id,
            "candidate_name": candidate.name,
            "extracted_data": extracted,
        }

    def _save_jd_to_db(self, extracted: dict, filename: str, db: Session, context: dict) -> dict:
        """Persist extracted JD → JobDescription table. Populates context."""
        jd_record = JobDescription(doc_name=filename, extracted_json=extracted)
        db.add(jd_record)
        db.commit()
        db.refresh(jd_record)

        context["jd_doc_name"] = filename
        context["jd_id"]       = jd_record.id

        logger.info(
            f"[{_ts()}] 💾 JD saved → id={jd_record.id} | doc_name='{filename}'"
        )
        return {
            "jd_id": jd_record.id,
            "jd_doc_name": filename,
            "extracted_data": extracted,
        }

    # ------------------------------------------------------------------
    # Public: run(context) — standard agent interface
    # ------------------------------------------------------------------

    def run(self, context: dict) -> dict:
        """
        Entry point called by the orchestrator.

        Cache logic:
          - Resume: checks Candidate WHERE source_filename = resume_filename
          - JD    : checks JobDescription WHERE doc_name = jd_filename
          → If found: returns DB data immediately, no LLM call
          → If not found: full extraction + save to DB
        """
        db: Session = context.get("db")
        results = {}

        # ── Resume ──────────────────────────────────────────────────────
        if context.get("resume_content"):
            filename = context["resume_filename"]

            cached = self._check_resume_cache(filename, db)
            if cached:
                # Cache hit — populate context and skip extraction
                context["candidate_id"]   = cached["candidate_id"]
                context["candidate_name"] = cached["candidate_name"]
                results["resume"] = cached
            else:
                # Cache miss — extract and save
                extracted = self._extract(context["resume_content"], filename, doc_type="resume")
                if "error" not in extracted and db:
                    results["resume"] = self._save_resume_to_db(extracted, filename, db, context)
                else:
                    results["resume"] = extracted

        # ── JD ──────────────────────────────────────────────────────────
        if context.get("jd_content"):
            filename = context["jd_filename"]

            cached = self._check_jd_cache(filename, db)
            if cached:
                # Cache hit — populate context and skip extraction
                context["jd_doc_name"] = cached["jd_doc_name"]
                context["jd_id"]       = cached["jd_id"]
                results["jd"] = cached
            else:
                # Cache miss — extract and save
                extracted_jd = self._extract(context["jd_content"], filename, doc_type="jd")
                if "error" not in extracted_jd and db:
                    results["jd"] = self._save_jd_to_db(extracted_jd, filename, db, context)
                else:
                    results["jd"] = extracted_jd

        return results


# Singleton
extraction_agent = ExtractionAgent()
