import os
import logging
from dotenv import load_dotenv

# Find the project root directory
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(project_root, '.env')

load_dotenv(dotenv_path=env_path if os.path.exists(env_path) else None, override=True)

logger = logging.getLogger("agents.gmail_agent.config")

# ── SMTP ──────────────────────────────────────────────────────────────────────
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")

try:
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
except ValueError:
    SMTP_PORT = 587

# ── Threshold ─────────────────────────────────────────────────────────────────
SHORTLISTING_THRESHOLD = float(os.getenv("SHORTLISTING_THRESHOLD", "90"))

# ── Shortlisting Email ────────────────────────────────────────────────────────
SHORTLIST_SUBJECT = "Interview Invitation – Next Steps"
SHORTLIST_BODY = """Hi {candidate_name},

Congratulations! Based on your profile, you have been shortlisted for the {role} position.

You have successfully cleared the resume screening stage and are now invited to participate
in the next round, which will be conducted by our AI-based interview system.

Further instructions for the AI interview will be shared with you shortly.

Thank you for your interest.

Best regards,
AI Hiring Team"""

# ── Rejection Email ───────────────────────────────────────────────────────────
REJECTION_SUBJECT = "Application Update – {role} Position"
REJECTION_BODY = """Hi {candidate_name},

Thank you for applying for the {role} position and for taking the time to go through our
screening process.

After careful review, we regret to inform you that your profile does not meet the requirements
for this particular role at this time.

We encourage you to continue developing your skills and to apply for future openings that
match your profile.

We appreciate your interest and wish you all the best in your career journey.

Best regards,
AI Hiring Team"""
