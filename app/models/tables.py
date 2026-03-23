from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=True)
    email = Column(String(255), index=True, nullable=True)
    phone = Column(String(50), nullable=True)

    # Original upload filename — used as deduplication key
    source_filename = Column(String(500), nullable=True, index=True)
    
    # Text data (Original docs)
    resume_text = Column(Text, nullable=True)
    interview_transcript = Column(Text, nullable=True)
    
    # JSON Structured data (Stored as TEXT in SQLite, natively as JSONB in Postgres)
    # SQLAlchemy handles the serialization automatically for us
    extracted_resume_json = Column(JSON, nullable=True)
    jd_json = Column(JSON, nullable=True)

    # Screening result — full scorecard from ScreeningAgent
    screening_result = Column(JSON, nullable=True)

    # Metrics and flags
    bias_flags = Column(JSON, nullable=True)
    interview_score = Column(Integer, nullable=True)
    
    # Meta
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Candidate(name={self.name}, email={self.email})>"


class JobDescription(Base):
    __tablename__ = "job_descriptions"

    id = Column(Integer, primary_key=True, index=True)

    # Original document filename — used as the lookup key by the screening agent
    doc_name = Column(String(500), nullable=False, index=True)

    # Full structured JSON extracted by the extraction agent
    extracted_json = Column(JSON, nullable=True)

    # Meta
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<JobDescription(doc_name={self.doc_name})>"


class InterviewSession(Base):
    """One interview session per candidate run."""
    __tablename__ = "interview_sessions"

    id = Column(Integer, primary_key=True, index=True)

    # Link to the candidate being interviewed
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False, index=True)
    candidate_name = Column(String(255), nullable=True)  # denormalised for quick display

    # Session lifecycle
    status = Column(String(50), default="active")   # active | completed | aborted
    question_count = Column(Integer, default=0)      # how many questions asked so far
    max_questions = Column(Integer, default=10)      # configurable cap

    # Evaluation — full bias/performance analysis result stored directly on session
    evaluation_result = Column(JSON, nullable=True)  # set by BiasDetectionAgent after completion
    report_path = Column(String(500), nullable=True) # path to generated .docx report

    # Meta
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)

    # Relationship
    messages = relationship("InterviewChat", back_populates="session",
                            cascade="all, delete-orphan", order_by="InterviewChat.timestamp")

    def __repr__(self):
        return f"<InterviewSession(id={self.id}, candidate='{self.candidate_name}', status='{self.status}')>"


class InterviewChat(Base):
    """Single Q&A turn within an interview session."""
    __tablename__ = "interview_chats"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("interview_sessions.id"), nullable=False, index=True)

    # Persisted for full audit trail
    candidate_name = Column(String(255), nullable=True)
    question_number = Column(Integer, nullable=False)  # 1-based
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)               # NULL until candidate replies

    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    session = relationship("InterviewSession", back_populates="messages")

    def __repr__(self):
        return f"<InterviewChat(session={self.session_id}, q={self.question_number})>"


class User(Base):
    """
    Unified user table for HR and Candidate logins.
    - HR signs up manually via the portal.
    - Candidates are auto-created with generated credentials when shortlisted.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True, nullable=False)
    email = Column(String(255), index=True, nullable=False)
    name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    age = Column(Integer, nullable=True)
    role = Column(String(50), nullable=False, default="hr")  # 'hr' | 'candidate'

    # For candidates — link to the Candidate table record
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<User(username={self.username}, role={self.role})>"
