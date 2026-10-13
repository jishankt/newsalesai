"""
Automated Test Suite for Kepler Tech SalesAI Offline Multi-Agent Jobs.
Validates:
1. Strict typing and grounding (missing values remain 'missing').
2. Malformed LLM JSON retry behavior.
3. Proposal isolation: production files are NEVER touched directly by jobs.
4. Human approval workflow: apply_proposal.py correctly dry-runs, lists, and applies proposals.
5. All 4 jobs (Enrichment, QA, Lead Brief, Policy Drift) execute correctly with mocked LLM.
6. Architectural boundary: chat runtime modules (app.py, routes, conversation, workflow) NEVER import jobs.
"""

import os
import json
import ast
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from pydantic import BaseModel, Field

from jobs.runner import JobRunner, JobProposal
from jobs.notifier import NotificationDispatcher, NotificationPayload
from jobs.job_lead_brief import JobLeadBrief, LeadBriefOutput
from jobs.job_product_enrichment import (
    JobProductEnrichment,
    ProductEnrichmentFields,
    extract_text_from_html,
)
from jobs.job_nightly_qa import JobNightlyQA, TurnQAScoreOutput
from jobs.job_policy_drift import JobPolicyDrift, ExtractedPolicySections
from scripts.apply_proposal import apply_proposal, load_proposal, list_proposals, reject_proposal


class DummyOutputSchema(BaseModel):
    required_key: str
    optional_key: str = "missing"
    numeric_stat: int = 0


@pytest.fixture
def temp_job_env(tmp_path):
    """Fixture providing isolated temporary directories for jobs and proposals."""
    old_cwd = os.getcwd()
    os.chdir(tmp_path)

    (tmp_path / "data" / "job_runs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "proposals").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "html_cache").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests" / "proposed").mkdir(parents=True, exist_ok=True)

    yield tmp_path

    os.chdir(old_cwd)


class TestJobRunnerCore:
    def test_mock_step_execution_success(self, temp_job_env):
        runner = JobRunner(job_name="test_runner")
        mock_data = {
            "required_key": "verified_value",
            "optional_key": "missing",
            "numeric_stat": 42,
        }

        result = runner.execute_step(
            step_name="step_1",
            system_instruction="Extract data",
            user_prompt="Get dummy data",
            evidence={"sample": "data"},
            output_schema=DummyOutputSchema,
            mock_response=mock_data,
        )

        assert result.required_key == "verified_value"
        assert result.optional_key == "missing"
        assert result.numeric_stat == 42
        assert len(runner.run_record.steps) == 1
        assert runner.run_record.steps[0].success is True

    def test_malformed_json_retry_handling(self, temp_job_env):
        """Simulates LLM returning invalid JSON on first attempt and valid on retry."""
        runner = JobRunner(job_name="test_retry_runner")

        mock_bad_resp = MagicMock()
        mock_bad_resp.status_code = 200
        mock_bad_resp.json.return_value = {"message": {"content": "INVALID JSON {"}}

        mock_good_resp = MagicMock()
        mock_good_resp.status_code = 200
        mock_good_resp.json.return_value = {
            "message": {
                "content": json.dumps({
                    "required_key": "recovered",
                    "optional_key": "missing",
                    "numeric_stat": 10,
                })
            }
        }

        with patch("requests.post", side_effect=[mock_bad_resp, mock_good_resp]):
            result = runner.execute_step(
                step_name="step_with_retry",
                system_instruction="Extract data",
                user_prompt="Get dummy data",
                evidence={"sample": "data"},
                output_schema=DummyOutputSchema,
            )

            assert result.required_key == "recovered"
            assert runner.run_record.steps[0].retries_count == 1
            assert runner.run_record.steps[0].success is True

    def test_save_proposal_isolation(self, temp_job_env):
        runner = JobRunner(job_name="test_prop_runner")
        target_file = str(temp_job_env / "data" / "production_target.json")

        proposal = runner.save_proposal(
            target_file=target_file,
            proposed_changes={"field_a": "new_val"},
            conflicts_reported=[{"field": "field_b", "conflict": "mismatch"}],
        )

        assert proposal.status == "pending"
        assert proposal.target_file == target_file
        # Assert proposal file was created in data/proposals
        proposal_file = temp_job_env / "data" / "proposals" / f"test_prop_runner_{proposal.proposal_id}.json"
        assert proposal_file.exists()
        # Assert production target file is NOT touched
        assert not Path(target_file).exists()


class TestNotificationDispatcher:
    def test_idempotent_dispatch(self, temp_job_env):
        disp_log = temp_job_env / "data" / "dispatched_notifications.json"
        dispatcher = NotificationDispatcher(dispatch_log_path=disp_log)

        payload = NotificationPayload(
            event_id="lead_101",
            channel="log",
            subject="New Lead",
            body="Details for lead",
        )

        res1 = dispatcher.dispatch(payload)
        assert res1.success is True
        assert res1.idempotent_skip is False

        # Second dispatch of same event_id should be skipped
        res2 = dispatcher.dispatch(payload)
        assert res2.success is True
        assert res2.idempotent_skip is True


class TestJobLeadBrief:
    def test_lead_brief_generation_and_dispatch(self, temp_job_env):
        runner = JobRunner(job_name="test_lead_brief")
        disp_log = temp_job_env / "data" / "dispatched_notifications.json"
        dispatcher = NotificationDispatcher(dispatch_log_path=disp_log)
        job = JobLeadBrief(runner=runner, notifier=dispatcher)

        lead = {
            "lead_id": 99,
            "customer_name": "Tariq Mansoor",
            "phone": "+971 50 123 4567",
            "product_interest": "Epson SC-T5405 Plotter",
            "notes": "Architectural studio looking for A0 CAD prints.",
        }

        mock_brief = {
            "lead_id": "99",
            "customer_name": "Tariq Mansoor",
            "phone": "+971 50 123 4567",
            "email": "missing",
            "company": "missing",
            "product_interest": "Epson SC-T5405 Plotter",
            "estimated_volume": "missing",
            "urgency": "high",
            "next_step": "Dispatch quotation for SC-T5405 with stand",
            "executive_brief": "Client requires an A0 CAD plotter for architectural drafting. Requested immediate follow-up.",
        }

        result = job.process_lead(lead, mock_response=mock_brief)
        assert result is not None
        assert result.customer_name == "Tariq Mansoor"
        assert result.email == "missing"
        assert result.urgency == "high"
        assert dispatcher.is_already_dispatched("lead_99")


class TestJobProductEnrichment:
    def test_enrichment_diff_and_missing_values(self, temp_job_env):
        cat_path = temp_job_env / "data" / "catalogue_products.json"
        current_catalogue = [
            {
                "id": "epson-sc-f100",
                "display_name": "Epson SureColor SC-F100",
                "model_family": "SC-F100",
                "print_speed": "Standard draft",
                "dpi": "600 x 1200 dpi",
                "product_url": "https://example.com/sc-f100",
            }
        ]
        with open(cat_path, "w", encoding="utf-8") as f:
            json.dump(current_catalogue, f)

        runner = JobRunner(job_name="test_enrichment")
        job = JobProductEnrichment(runner=runner, catalogue_path=cat_path)

        mock_enriched = {
            "model_id": "epson-sc-f100",
            "specs": {
                "dpi": "600 x 1200 dpi",  # Same, no conflict
                "dimensions": "375 x 347 x 187 mm",  # New spec
            },
            "connectivity": ["Wi-Fi", "USB 2.0", "Ethernet"],
            "accessories": [],
            "consumables": ["T49N1", "T49N2", "T49N3", "T49N4"],
            "media_compatibility": ["Dye-sublimation transfer paper"],
            "warranty": "1 Year Commercial Warranty",
            "use_cases": ["Mugs", "Phone cases", "Custom gifts"],
            "best_for": ["Small photo studios and promotional gift shops"],
            "not_ideal_for": ["High-volume industrial textile roll printing"],
            "source_urls": {"warranty": "https://example.com/sc-f100"},
            "missing_fields": ["power_consumption", "memory"],
        }

        proposal = job.enrich_product(current_catalogue[0], mock_response=mock_enriched)
        assert proposal is not None
        assert proposal.status == "pending"
        assert proposal.proposed_changes["model_id"] == "epson-sc-f100"
        assert "connectivity" in proposal.proposed_changes["updates"]
        assert proposal.proposed_changes["updates"]["warranty"] == "1 Year Commercial Warranty"

        # Verify catalogue file was NOT modified directly
        with open(cat_path, "r", encoding="utf-8") as f:
            unmodified_cat = json.load(f)
            assert "connectivity" not in unmodified_cat[0]


class TestJobNightlyQA:
    def test_qa_evaluates_turn_and_drafts_tests(self, temp_job_env):
        runner = JobRunner(job_name="test_qa")
        job = JobNightlyQA(runner=runner)

        turn = {
            "turn_id": "session_abc_t0",
            "user_message": "Can I get the price for the SC-P700?",
            "assistant_message": "Certainly! I am delighted to assist. The price is AED 3,500.",
        }

        mock_qa_output = {
            "turn_id": "session_abc_t0",
            "answers_the_question": True,
            "model_consistency": True,
            "fact_grounding": False,
            "naturalness": 2.1,
            "failure_pattern": "banned_boilerplate",
            "explanation": "Contained banned corporate opening phrases and ungrounded direct price quote.",
        }

        score = job.evaluate_turn(turn, mock_response=mock_qa_output)
        assert score.naturalness == 2.1
        assert score.failure_pattern == "banned_boilerplate"

        # Verify draft regression test creation
        drafted_file = job.draft_regression_tests([(turn, score)])
        assert drafted_file is not None
        assert drafted_file.exists()
        assert "test_qa_regression_turn_0" in drafted_file.read_text()


class TestJobPolicyDrift:
    def test_policy_drift_conflict_detection(self, temp_job_env):
        runner = JobRunner(job_name="test_drift")
        policy_path = temp_job_env / "data" / "delivery_policy.json"
        baseline = {
            "delivery_fee_uae": "flat AED 10",
            "dispatch_timing": "1 to 2 business days",
            "defect_reporting_window": "within 2 days of receipt",
        }
        with open(policy_path, "w", encoding="utf-8") as f:
            json.dump(baseline, f)

        job = JobPolicyDrift(runner=runner, policy_path=policy_path)

        mock_drifted_terms = {
            "source_url": "https://www.keplertechllc.com/terms-conditions/",
            "delivery_fee_uae": "flat AED 15",  # DRIFT: Changed from AED 10 to AED 15
            "delivery_fee_international": "calculated at checkout",
            "dispatch_timing": "1 to 2 business days",
            "pickup_policy": "free store pickup",
            "payment_terms": "payment in full before dispatch",
            "defect_reporting_window": "within 5 days of receipt",  # DRIFT: Changed from 2 to 5 days
            "cancellation_window": "within 24 hours",
            "ofac_sanctions_policy": "no trade with OFAC countries",
            "business_hours": "Mon-Fri 8:30-17:30",
            "missing_sections": [],
        }

        proposal = job.run(mock_response=mock_drifted_terms)
        assert proposal is not None
        assert len(proposal.conflicts_reported) >= 2
        conflicted_keys = [c["policy_key"] for c in proposal.conflicts_reported]
        assert "delivery_fee_uae" in conflicted_keys
        assert "defect_reporting_window" in conflicted_keys


class TestApplyProposalCLI:
    def test_apply_proposal_dry_run_and_execution(self, temp_job_env):
        target_file = temp_job_env / "data" / "target.json"
        init_data = [{"id": "model_1", "spec": "old_value"}]
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(init_data, f)

        runner = JobRunner(job_name="cli_test")
        proposal = runner.save_proposal(
            target_file=str(target_file),
            proposed_changes={"model_id": "model_1", "updates": {"spec": "new_value"}},
        )

        p_id = proposal.proposal_id

        # 1. Dry run: should NOT modify file
        ret_dry = apply_proposal(p_id, dry_run=True, approved_by="test_admin")
        assert ret_dry == 0
        with open(target_file, "r", encoding="utf-8") as f:
            curr = json.load(f)
            assert curr[0]["spec"] == "old_value"

        # 2. Live apply: should modify file and mark proposal applied
        ret_apply = apply_proposal(p_id, dry_run=False, approved_by="test_admin")
        assert ret_apply == 0
        with open(target_file, "r", encoding="utf-8") as f:
            updated = json.load(f)
            assert updated[0]["spec"] == "new_value"

        path, prop_data = load_proposal(p_id)
        assert prop_data["status"] == "applied"
        assert prop_data["approved_by"] == "test_admin"


class TestArchitecturalImportBoundary:
    """Verifies that no chat or runtime module imports offline jobs."""

    def test_jobs_not_imported_by_chat_modules(self):
        project_root = Path("/opt/salesai")
        chat_paths = [
            project_root / "app.py",
            *(project_root / "routes").glob("*.py"),
            *(project_root / "conversation").glob("*.py"),
            *(project_root / "workflow").rglob("*.py"),
        ]

        illegal_imports = []
        for py_path in chat_paths:
            if not py_path.exists() or "__pycache__" in str(py_path):
                continue
            with open(py_path, "r", encoding="utf-8") as f:
                content = f.read()
                try:
                    tree = ast.parse(content, filename=str(py_path))
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                if alias.name == "jobs" or alias.name.startswith("jobs."):
                                    illegal_imports.append((str(py_path), alias.name))
                        elif isinstance(node, ast.ImportFrom):
                            if node.module == "jobs" or (node.module and node.module.startswith("jobs.")):
                                illegal_imports.append((str(py_path), node.module))
                except SyntaxError:
                    pass

        assert illegal_imports == [], f"Found illegal imports of offline jobs in chat runtime: {illegal_imports}"
