"""
Orchestrator Agent  —  Pure LLM Router
=======================================
Responsibilities (ONLY):
  1. Maintain an agent registry (name → description + agent instance)
  2. Ask Gemini which agents to run for a given request (LLM Router)
  3. Call each agent's run(context) in the planned order
  4. Merge and return results

NO business logic lives here.
Each agent owns its own tools, prompts, and DB operations.
"""

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Protocol

from dotenv import load_dotenv
from google import genai
from google.genai import types
from sqlalchemy.orm import Session

from agents.extraction_agent.agent import extraction_agent
from agents.screening_agent.agent import screening_agent
from agents.gmail_agent.agent import gmail_agent
from agents.orchestrator.prompts import ROUTING_PROMPT

load_dotenv()

logger = logging.getLogger("agents.orchestrator")


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ---------------------------------------------------------------------------
# Agent Protocol — every sub-agent must implement run(context) -> dict
# ---------------------------------------------------------------------------

class AgentProtocol(Protocol):
    DESCRIPTION: str
    def run(self, context: dict) -> dict: ...


# ---------------------------------------------------------------------------
# Registry Entry
# ---------------------------------------------------------------------------

@dataclass
class AgentSpec:
    name: str
    description: str   # shown to the LLM router
    agent: Any         # instance implementing AgentProtocol


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class OrchestratorAgent:

    MODEL_NAME = "gemini-2.5-flash"

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("[OrchestratorAgent] GEMINI_API_KEY is not set.")
        self.client = genai.Client(api_key=api_key)

        # ── Registry ────────────────────────────────────────────────────
        # To add a new agent: import its singleton + add ONE AgentSpec here.
        self.registry: dict[str, AgentSpec] = {
            "extraction": AgentSpec(
                name="extraction",
                description=extraction_agent.DESCRIPTION,
                agent=extraction_agent,
            ),
            "screening": AgentSpec(
                name="screening",
                description=screening_agent.DESCRIPTION,
                agent=screening_agent,
            ),
            "gmail": AgentSpec(
                name="gmail",
                description=gmail_agent.DESCRIPTION,
                agent=gmail_agent,
            ),
            # "bias_check": AgentSpec(
            #     name="bias_check",
            #     description=bias_check_agent.DESCRIPTION,
            #     agent=bias_check_agent,
            # ),
            # "interview": AgentSpec(
            #     name="interview",
            #     description=interview_agent.DESCRIPTION,
            #     agent=interview_agent,
            # ),
        }

        logger.info(
            f"[{_ts()}] OrchestratorAgent ready | "
            f"registered agents: {list(self.registry.keys())}"
        )

    # ------------------------------------------------------------------
    # LLM Router
    # ------------------------------------------------------------------

    def _ask_llm_for_plan(self, routing_context: dict) -> list[str]:
        """Ask Gemini which agents to run. Returns ordered list of agent names."""
        agent_descriptions = "\n".join(
            f"{i}. [{spec.name}] — {spec.description}"
            for i, spec in enumerate(self.registry.values(), 1)
        )
        prompt = ROUTING_PROMPT.format(
            agent_descriptions=agent_descriptions,
            request_context=json.dumps(routing_context, indent=2),
        )

        logger.info(f"[{_ts()}] 🧭 LLM Router — deciding plan...")
        t0 = time.perf_counter()
        try:
            response = self.client.models.generate_content(
                model=self.MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            result = json.loads(response.text)
            plan: list[str] = result.get("plan", [])
            reasoning: str = result.get("reasoning", "")

            # Validate against registry
            valid_plan = [a for a in plan if a in self.registry]
            unknown = [a for a in plan if a not in self.registry]
            if unknown:
                logger.warning(f"[{_ts()}] ⚠ Router returned unknown agents (ignored): {unknown}")

            logger.info(
                f"[{_ts()}] ✅ Plan in {time.perf_counter()-t0:.2f}s → "
                f"{valid_plan} | Reason: {reasoning}"
            )
            return valid_plan

        except Exception as exc:
            logger.error(
                f"[{_ts()}] ❌ LLM Router failed: {exc} — falling back to ['extraction']"
            )
            return ["extraction"]

    # ------------------------------------------------------------------
    # Public Entry Point
    # ------------------------------------------------------------------

    def run(
        self,
        db: Session,
        resume_content: Optional[bytes] = None,
        resume_filename: Optional[str] = None,
        jd_content: Optional[bytes] = None,
        jd_filename: Optional[str] = None,
        instructions: Optional[str] = None,
    ) -> dict:
        """
        Single entry point for all upload requests.

        Steps:
          1. Build routing context (metadata only — no raw bytes)
          2. Ask LLM which agents to run → get ordered plan
          3. Execute each agent: agent.run(context)
          4. Return merged results
        """
        t0 = time.perf_counter()
        logger.info(
            f"[{_ts()}] ▶▶ OrchestratorAgent.run | "
            f"resume={resume_filename} | jd={jd_filename}"
        )

        # Shared execution context passed to every agent
        context: dict[str, Any] = {
            "db": db,
            "resume_content": resume_content,
            "resume_filename": resume_filename,
            "jd_content": jd_content,
            "jd_filename": jd_filename,
        }

        # Routing context — serialisable, sent to LLM
        routing_context = {
            "uploaded_documents": {
                "resume": resume_filename if resume_content else None,
                "jd": jd_filename if jd_content else None,
            },
            "additional_instructions": instructions or "none",
            "available_agents": list(self.registry.keys()),
        }

        # Step 1: LLM decides the plan
        plan = self._ask_llm_for_plan(routing_context)

        # Step 2: Execute each agent in plan order
        all_results: dict[str, Any] = {}
        for agent_name in plan:
            spec = self.registry[agent_name]
            logger.info(f"[{_ts()}] ⚙ Running agent: [{agent_name}]")
            step_t0 = time.perf_counter()
            try:
                all_results[agent_name] = spec.agent.run(context)
                logger.info(
                    f"[{_ts()}] ✅ [{agent_name}] done in "
                    f"{time.perf_counter()-step_t0:.2f}s"
                )
            except Exception as exc:
                logger.error(f"[{_ts()}] ❌ [{agent_name}] error: {exc}")
                all_results[agent_name] = {"error": str(exc)}

        total = time.perf_counter() - t0
        logger.info(f"[{_ts()}] ✅✅ Orchestrator done | plan={plan} | total={total:.2f}s")

        return {
            "status": "success",
            "plan_executed": plan,
            "candidate_id": context.get("candidate_id"),
            "results": all_results,
            "total_latency_seconds": round(total, 4),
        }


# Singleton
orchestrator_agent = OrchestratorAgent()
