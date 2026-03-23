"""
Auth Routes
===========
Sign-up (HR only), Login (HR + Candidate), and candidate credentials generation.

Endpoints
---------
POST /auth/signup               — HR sign-up (creates user with role='hr')
POST /auth/login                — Login for HR and Candidate
POST /auth/generate-candidate   — Generates random username/password for a candidate,
                                  stores in users table, and emails the credentials
GET  /auth/me/{username}        — Get user profile by username
"""

import logging
import os
import random
import string
import hashlib

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.tables import User, Candidate
from agents.gmail_agent.gmail_agent import email_sender

logger = logging.getLogger("app.routes.auth")

router = APIRouter(prefix="/auth", tags=["Auth"])


# ── Request / Response Schemas ────────────────────────────────────────────────

class SignupRequest(BaseModel):
    name: str = Field(..., min_length=2)
    email: str = Field(...)
    password: str = Field(..., min_length=4)
    age: int = Field(..., ge=18, le=100)
    role: str = Field(default="hr")  # Only 'hr' allowed at signup


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class GenerateCandidateRequest(BaseModel):
    candidate_id: int = Field(..., description="Candidate ID from candidates table")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    """Simple SHA-256 hash for password storage."""
    return hashlib.sha256(password.encode()).hexdigest()


def _generate_password(length: int = 10) -> str:
    """Generate a random alphanumeric password."""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/signup", summary="HR Sign-up")
async def signup(body: SignupRequest, db: Session = Depends(get_db)):
    """
    HR sign-up only. Creates a new user with role='hr'.
    Username is auto-generated from the email (part before @).
    """
    if body.role != "hr":
        raise HTTPException(status_code=400, detail="Only HR role can sign up via this portal.")

    # Check if email already exists
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    # Generate username from email
    username = body.email.split("@")[0]

    # Check if username exists, append random digits if so
    base_username = username
    while db.query(User).filter(User.username == username).first():
        username = f"{base_username}{random.randint(100, 999)}"

    user = User(
        username=username,
        email=body.email,
        name=body.name,
        password_hash=_hash_password(body.password),
        age=body.age,
        role="hr",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info(f"[Auth] HR sign-up: {user.username} ({user.email})")

    return {
        "status": "success",
        "message": "Account created successfully.",
        "user": {
            "id": user.id,
            "username": user.username,
            "name": user.name,
            "email": user.email,
            "role": user.role,
        },
    }


@router.post("/login", summary="Login (HR + Candidate)")
async def login(body: LoginRequest, db: Session = Depends(get_db)):
    """
    Login for both HR and Candidate users.
    Validates username + password against the users table.
    """
    user = db.query(User).filter(User.username == body.username).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    if user.password_hash != _hash_password(body.password):
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    logger.info(f"[Auth] Login: {user.username} (role={user.role})")

    response = {
        "status": "success",
        "user": {
            "id": user.id,
            "username": user.username,
            "name": user.name,
            "email": user.email,
            "role": user.role,
        },
    }

    # If candidate, also include candidate_id for fetching interview data
    if user.role == "candidate" and user.candidate_id:
        response["user"]["candidate_id"] = user.candidate_id

    return response


@router.post("/generate-candidate", summary="Generate candidate credentials & email them")
async def generate_candidate_credentials(
    body: GenerateCandidateRequest,
    db: Session = Depends(get_db),
):
    """
    Generates random username + password for a candidate:
    1. Fetches candidate name/email from candidates table
    2. Creates username from candidate name
    3. Generates random password
    4. Stores in users table with role='candidate'
    5. Emails the credentials to the candidate
    """
    candidate = db.query(Candidate).filter(Candidate.id == body.candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail=f"Candidate ID {body.candidate_id} not found.")

    if not candidate.email:
        raise HTTPException(status_code=400, detail="Candidate has no email address.")

    # Check if credentials already exist for this candidate
    existing = db.query(User).filter(
        User.candidate_id == body.candidate_id,
        User.role == "candidate"
    ).first()
    if existing:
        return {
            "status": "already_exists",
            "message": "Credentials already generated for this candidate.",
            "username": existing.username,
        }

    # Generate username from candidate name
    candidate_name = candidate.name or "candidate"
    base_username = candidate_name.lower().replace(" ", "_").replace(".", "_")
    username = base_username
    while db.query(User).filter(User.username == username).first():
        username = f"{base_username}{random.randint(100, 999)}"

    # Generate random password
    raw_password = _generate_password(10)

    # Create user record
    user = User(
        username=username,
        email=candidate.email,
        name=candidate_name,
        password_hash=_hash_password(raw_password),
        role="candidate",
        candidate_id=body.candidate_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Email credentials to candidate
    subject = "Your Interview Portal Credentials"
    body_text = f"""Hi {candidate_name},

Congratulations on being shortlisted! You can now access the HR-Bot Interview Portal.

Your login credentials:
  Username: {username}
  Password: {raw_password}

Please log in at the portal to begin your interview process.

Best regards,
AI Hiring Team"""

    email_sent = email_sender.send(candidate.email, subject, body_text)

    logger.info(
        f"[Auth] Candidate credentials generated: {username} | "
        f"email_sent={email_sent} | candidate_id={body.candidate_id}"
    )

    return {
        "status": "success",
        "message": "Credentials generated and emailed.",
        "username": username,
        "password": raw_password,  # returned once for HR to see
        "email_sent": email_sent,
        "candidate_id": body.candidate_id,
    }


@router.get("/me/{username}", summary="Get user profile")
async def get_user_profile(username: str, db: Session = Depends(get_db)):
    """Fetch user profile by username."""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    response = {
        "id": user.id,
        "username": user.username,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "age": user.age,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
    if user.role == "candidate" and user.candidate_id:
        response["candidate_id"] = user.candidate_id

    return response
