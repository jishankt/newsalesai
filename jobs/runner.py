"""
Offline Multi-Agent Step Runner for Kepler Tech SalesAI.
Executes tool-grounded, typed LLM steps using local Ollama.
Guarantees:
- Strictly typed Pydantic inputs and outputs (no free-text handoffs)
- Facts strictly grounded in supplied evidence; missing values stay 'missing'
- Configurable model, temperature 0, timeouts, 1-retry on malformed JSON
- Comprehensive run logs in data/job_runs/
- Proposals saved to data/proposals/ for human approval
"""

import os
import json
import time
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Type, TypeVar
import requests
from pydantic import BaseModel, Field, ValidationError

from config import (
    OLLAMA_BASE_URL,
    JOB_MODEL,
    JOB_TIMEOUT_SECONDS,
    JOB_MAX_RETRIES,
)

logger = logging.getLogger("jobs.runner")

T = TypeVar("T", bound=BaseModel)


class StepExecutionLog(BaseModel):
    step_name: str
    model: str
    started_at: str
    completed_at: str
    duration_ms: int
    inputs: Dict[str, Any]
    evidence_summary: str
    raw_response: Optional[str] = None
    parsed_output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retries_count: int = 0
    success: bool = True


class JobRunRecord(BaseModel):
    run_id: str
    job_name: str
    started_at: str
    completed_at: Optional[str] = None
    total_duration_ms: Optional[int] = None
    status: str = "running"  # "completed", "failed", "partial"
    steps: List[StepExecutionLog] = Field(default_factory=list)
    proposals_generated: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class JobProposal(BaseModel):
    proposal_id: str
    job_name: str
    created_at: str
    target_file: str
    proposed_changes: Dict[str, Any]
    conflicts_reported: List[Dict[str, Any]] = Field(default_factory=list)
    requires_human_approval: bool = True
    approved_by: Optional[str] = None
    applied_at: Optional[str] = None
    status: str = "pending"  # "pending", "approved", "rejected", "applied"


class JobRunner:
    """Orchestrates typed multi-step jobs with local Ollama validation."""

    def __init__(
        self,
        job_name: str,
        model: Optional[str] = None,
        base_url: str = OLLAMA_BASE_URL,
        timeout: float = JOB_TIMEOUT_SECONDS,
    ):
        self.job_name = job_name
        self.model = model or JOB_MODEL
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.run_id = f"{job_name}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self.run_record = JobRunRecord(
            run_id=self.run_id,
            job_name=job_name,
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        self.runs_dir = Path("data/job_runs")
        self.proposals_dir = Path("data/proposals")
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.proposals_dir.mkdir(parents=True, exist_ok=True)

    def execute_step(
        self,
        step_name: str,
        system_instruction: str,
        user_prompt: str,
        evidence: Dict[str, Any],
        output_schema: Type[T],
        mock_response: Optional[Dict[str, Any]] = None,
    ) -> T:
        """
        Executes a single typed step:
        1. Packs evidence + prompt.
        2. Queries Ollama with temperature=0 and json format.
        3. Validates against Pydantic schema.
        4. If malformed JSON, retries once with error context.
        5. Logs step inputs, outputs, evidence, and latency.
        """
        start_t = time.time()
        start_iso = datetime.now(timezone.utc).isoformat()
        retries = 0
        error_msg = None
        parsed_obj: Optional[T] = None
        raw_output_text: Optional[str] = None

        evidence_str = json.dumps(evidence, indent=2, default=str)
        evidence_summary = f"Keys: {list(evidence.keys())} | Length: {len(evidence_str)} chars"

        # Schema guidelines injected into system instruction
        schema_spec = json.dumps(output_schema.model_json_schema(), indent=2)
        full_system = (
            f"{system_instruction}\n\n"
            "CRITICAL INSTRUCTIONS:\n"
            "1. You MUST answer ONLY from the provided evidence. Do NOT assume, extrapolate, or guess.\n"
            "2. If an attribute or value is not explicitly documented in the evidence, set its status or value to 'missing'.\n"
            "3. Output MUST be valid JSON conforming strictly to this JSON Schema:\n"
            f"{schema_spec}\n"
        )

        full_prompt = (
            f"--- VERIFIED EVIDENCE ---\n{evidence_str}\n\n"
            f"--- TASK REQUEST ---\n{user_prompt}\n"
        )

        # Handle Mocked Execution (e.g. during unit tests or when Ollama is mocked)
        if mock_response is not None:
            try:
                parsed_obj = output_schema.model_validate(mock_response)
                raw_output_text = json.dumps(mock_response)
            except ValidationError as ve:
                error_msg = f"Mock response validation failed: {ve}"
        else:
            # Live Ollama call with 1 retry on malformed JSON
            for attempt in range(JOB_MAX_RETRIES + 1):
                try:
                    payload = {
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": full_system},
                            {"role": "user", "content": full_prompt if attempt == 0 else f"{full_prompt}\n\nPREVIOUS ERROR: Your previous response was invalid JSON or failed schema validation: {error_msg}. Return strict valid JSON conforming to the schema."},
                        ],
                        "format": "json",
                        "stream": False,
                        "options": {
                            "temperature": 0.0,
                            "num_ctx": 8192,
                        },
                    }
                    if "qwen3" in self.model:
                        payload["options"]["thinking"] = False

                    resp = requests.post(
                        f"{self.base_url}/api/chat",
                        json=payload,
                        timeout=self.timeout,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    msg_content = data.get("message", {}).get("content", "")
                    raw_output_text = msg_content

                    # Parse JSON
                    clean_content = msg_content.strip()
                    if clean_content.startswith("```"):
                        clean_content = clean_content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

                    parsed_json = json.loads(clean_content)
                    parsed_obj = output_schema.model_validate(parsed_json)
                    error_msg = None
                    break  # Success
                except (json.JSONDecodeError, ValidationError) as parse_err:
                    error_msg = str(parse_err)
                    retries += 1
                    logger.warning(f"Step '{step_name}' attempt {attempt + 1} validation failed: {parse_err}. Retrying...")
                except Exception as req_err:
                    error_msg = f"Ollama HTTP error: {req_err}"
                    retries += 1
                    logger.error(f"Step '{step_name}' HTTP failure: {req_err}")
                    break

        duration_ms = int((time.time() - start_t) * 1000)
        end_iso = datetime.now(timezone.utc).isoformat()

        step_log = StepExecutionLog(
            step_name=step_name,
            model=self.model,
            started_at=start_iso,
            completed_at=end_iso,
            duration_ms=duration_ms,
            inputs={"prompt": user_prompt, "evidence_keys": list(evidence.keys())},
            evidence_summary=evidence_summary,
            raw_response=raw_output_text,
            parsed_output=parsed_obj.model_dump() if parsed_obj else None,
            error=error_msg,
            retries_count=retries,
            success=parsed_obj is not None,
        )
        self.run_record.steps.append(step_log)

        if parsed_obj is None:
            raise RuntimeError(f"Step '{step_name}' failed after {retries} retries: {error_msg}")

        return parsed_obj

    def save_proposal(
        self,
        target_file: str,
        proposed_changes: Dict[str, Any],
        conflicts_reported: Optional[List[Dict[str, Any]]] = None,
    ) -> JobProposal:
        """
        Human approval gate: writes proposed modifications to data/proposals/*.json.
        NEVER touches production data directly.
        """
        prop_id = f"prop_{uuid.uuid4().hex[:8]}"
        proposal = JobProposal(
            proposal_id=prop_id,
            job_name=self.job_name,
            created_at=datetime.now(timezone.utc).isoformat(),
            target_file=target_file,
            proposed_changes=proposed_changes,
            conflicts_reported=conflicts_reported or [],
        )

        prop_path = self.proposals_dir / f"{self.job_name}_{prop_id}.json"
        with open(prop_path, "w", encoding="utf-8") as f:
            f.write(proposal.model_dump_json(indent=2))

        self.run_record.proposals_generated.append(str(prop_path))
        logger.info(f"Generated human approval proposal at: {prop_path}")
        return proposal

    def finalize(self, error: Optional[str] = None):
        """Finalizes run record and writes run log to data/job_runs/."""
        self.run_record.completed_at = datetime.now(timezone.utc).isoformat()
        if self.run_record.steps:
            self.run_record.total_duration_ms = sum(s.duration_ms for s in self.run_record.steps)
        if error:
            self.run_record.status = "failed"
            self.run_record.error = error
        else:
            self.run_record.status = "completed"

        log_path = self.runs_dir / f"{self.run_id}.json"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(self.run_record.model_dump_json(indent=2))

        logger.info(f"Job '{self.job_name}' run record written to: {log_path}")
        return self.run_record


# Helper alias
JobStep = StepExecutionLog
