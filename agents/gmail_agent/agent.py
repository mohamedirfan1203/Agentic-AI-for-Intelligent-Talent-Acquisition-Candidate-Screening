"""
Gmail Agent
===========
Sub-agent that automatically sends email to a candidate after screening.

Rules:
  - overall_fit >= 90  → Shortlisting / Interview Invitation email
  - overall_fit <  90  → Polite rejection email

Interface: run(context: dict) -> dict
Context keys consumed:
  - candidate_name      (set by extraction agent)
  - screening_result    (set by screening agent — contains scores + recommendation)
  - db                  (SQLAlchemy Session — to fetch candidate's email)
"""

import logging
import time
from datetime import datetime

from sqlalchemy.orm import Session

from agents.gmail_agent.config import (
    SHORTLISTING_THRESHOLD,
    SHORTLIST_SUBJECT,
    SHORTLIST_BODY,
    REJECTION_SUBJECT,
    REJECTION_BODY,
)
from agents.gmail_agent.gmail_agent import email_sender
from app.models.tables import Candidate

logger = logging.getLogger("agents.gmail_agent")


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


class GmailAgent:
    """
    Gmail notification sub-agent.
    Owns: candidate email lookup, email content selection, sending via SMTP.
    """

    DESCRIPTION = (
        "Sends an email notification to the candidate after screening is complete. "
        f"If overall_fit score >= {SHORTLISTING_THRESHOLD}, sends a shortlisting / interview "
        "invitation email. If below the threshold, sends a polite rejection email. "
        "Must run after the screening agent."
    )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fetch_candidate_email(self, candidate_name: str, db: Session) -> tuple[str | None, str | None]:
        """Return (email, role_applied) for the candidate. Role is best-effort."""
        candidate = (
            db.query(Candidate)
            .filter(Candidate.name.ilike(f"%{candidate_name}%"))
            .order_by(Candidate.created_at.desc())
            .first()
        )
        if not candidate:
            logger.warning(f"[{_ts()}] ⚠ No candidate found for '{candidate_name}'")
            return None, None
        return candidate.email, candidate.name

    def _build_email(self, candidate_name: str, role: str, score: float) -> tuple[str, str]:
        """Return (subject, body) based on score threshold."""
        if score >= SHORTLISTING_THRESHOLD:
            subject = SHORTLIST_SUBJECT
            body = SHORTLIST_BODY.format(
                candidate_name=candidate_name,
                role=role,
            )
        else:
            subject = REJECTION_SUBJECT.format(role=role)
            body = REJECTION_BODY.format(
                candidate_name=candidate_name,
                role=role,
            )
        return subject, body

    # ------------------------------------------------------------------
    # Public: run(context) — standard agent interface
    # ------------------------------------------------------------------

    def run(self, context: dict) -> dict:
        """
        Entry point called by the orchestrator.

        Reads from context:
          - candidate_name    → used to fetch email from Candidate table
          - screening_result  → dict containing scores.overall_fit + jd_title
          - db                → SQLAlchemy session

        Returns result dict with email status.
        """
        t0 = time.perf_counter()
        db: Session = context.get("db")
        candidate_name: str = context.get("candidate_name", "Candidate")
        screening_result: dict = context.get("screening_result", {})

        # Extract score and role from screening result
        overall_fit: float = screening_result.get("scores", {}).get("overall_fit", 0)
        role: str = screening_result.get("jd_title", "the applied position")
        recommendation: str = screening_result.get("recommendation", "N/A")

        logger.info(
            f"[{_ts()}] ── GmailAgent START | "
            f"candidate='{candidate_name}' | score={overall_fit} | threshold={SHORTLISTING_THRESHOLD}"
        )

        # Step 1: Fetch candidate email from DB
        to_email, _ = self._fetch_candidate_email(candidate_name, db)
        if not to_email:
            logger.error(f"[{_ts()}] ❌ No email found for '{candidate_name}' — cannot send")
            return {
                "status": "failed",
                "reason": f"No email found in DB for candidate '{candidate_name}'",
            }

        # Step 2: Decide email type
        email_type = "shortlisting" if overall_fit >= SHORTLISTING_THRESHOLD else "rejection"
        logger.info(
            f"[{_ts()}] 📬 Email type: {email_type.upper()} | to: {to_email}"
        )

        # Step 3: Build and send
        subject, body = self._build_email(candidate_name, role, overall_fit)
        success = email_sender.send(to_email, subject, body)

        total = time.perf_counter() - t0
        if success:
            logger.info(
                f"[{_ts()}] ✅ GmailAgent DONE | {email_type} email sent to {to_email} | "
                f"total={total:.2f}s"
            )
            return {
                "status": "sent",
                "email_type": email_type,
                "to": to_email,
                "candidate_name": candidate_name,
                "overall_fit_score": overall_fit,
                "recommendation": recommendation,
            }
        else:
            logger.error(f"[{_ts()}] ❌ GmailAgent FAILED | could not send to {to_email}")
            return {
                "status": "failed",
                "reason": "SMTP send failed after retries",
                "to": to_email,
            }


# Singleton
gmail_agent = GmailAgent()
