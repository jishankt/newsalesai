"""
Offline Multi-Agent Job: Nightly Conversation Quality Assurance (QA).
Ingests conversations from conversations.db and data/review_queue.jsonl.
Evaluates turns against accuracy, grounding, model consistency, and human naturalness.
Clusters failure patterns and auto-drafts proposed pytest regression tests in tests/proposed/.
Generates daily markdown report at docs/NIGHTLY_QA_REPORT.md.
"""

import os
import sys
import json
import sqlite3
import time
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from config import QA_NATURALNESS_RUBRIC
from jobs.runner import JobRunner

logger = logging.getLogger("jobs.nightly_qa")

DB_PATH = Path("data/conversations.db")
REVIEW_QUEUE_PATH = Path("data/review_queue.jsonl")
PROPOSED_TESTS_DIR = Path("tests/proposed")
QA_REPORT_PATH = Path("docs/NIGHTLY_QA_REPORT.md")


class TurnQAScoreOutput(BaseModel):
    turn_id: str
    answers_the_question: bool = True
    model_consistency: bool = True
    fact_grounding: bool = True
    naturalness: float = Field(..., ge=1.0, le=5.0)
    failure_pattern: str = "none"  # "generic_fallback", "model_hallucination", "unanswered_question", "banned_boilerplate", "none"
    explanation: str


class JobNightlyQA:
    def __init__(self, runner: Optional[JobRunner] = None, db_path: Path = DB_PATH):
        self.runner = runner or JobRunner(job_name="nightly_qa")
        self.db_path = Path(db_path)
        PROPOSED_TESTS_DIR.mkdir(parents=True, exist_ok=True)

    def load_turns_to_evaluate(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Loads user-assistant turns from review_queue.jsonl and recent sessions in SQLite.
        """
        turns: List[Dict[str, Any]] = []

        # 1. From review queue if available
        if REVIEW_QUEUE_PATH.exists():
            try:
                with open(REVIEW_QUEUE_PATH, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            item = json.loads(line)
                            turns.append(item)
            except Exception as e:
                logger.warning(f"Error reading review queue: {e}")

        # 2. From SQLite database sessions
        if len(turns) < limit and self.db_path.exists():
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(
                    "SELECT session_id, history_json, updated_at FROM conversation_sessions ORDER BY updated_at DESC LIMIT ?",
                    (limit * 2,),
                )
                rows = cur.fetchall()
                for row in rows:
                    session_id = row["session_id"]
                    try:
                        history = json.loads(row["history_json"] or "[]")
                        # Pair user turn with subsequent assistant turn
                        for i in range(len(history) - 1):
                            if history[i].get("role") == "user" and history[i+1].get("role") == "assistant":
                                turns.append({
                                    "turn_id": f"{session_id}_t{i}",
                                    "session_id": session_id,
                                    "user_message": history[i].get("content", ""),
                                    "assistant_message": history[i+1].get("content", ""),
                                    "chips": history[i+1].get("chips", []),
                                })
                                if len(turns) >= limit:
                                    break
                    except Exception:
                        pass
                    if len(turns) >= limit:
                        break
                conn.close()
            except Exception as e:
                logger.warning(f"Error reading conversations from db: {e}")

        return turns[:limit]

    def evaluate_turn(
        self,
        turn: Dict[str, Any],
        mock_response: Optional[Dict[str, Any]] = None,
    ) -> TurnQAScoreOutput:
        turn_id = turn.get("turn_id", f"turn_{int(time.time()*1000)}")
        user_msg = turn.get("user_message", "")
        bot_msg = turn.get("assistant_message", "")

        # Deterministic checks first
        banned_phrases = ["Certainly!", "delighted to assist", "Based on your requirements"]
        has_banned = any(b in bot_msg for b in banned_phrases)
        has_leaked_tags = "{{" in bot_msg or "}}" in bot_msg or "<prompt>" in bot_msg
        is_generic_fallback = "I apologize, but I am unable to" in bot_msg or "As an AI" in bot_msg

        system_instruction = (
            "You are a Quality Assurance Judge evaluating conversational AI turns for Kepler Tech LLC.\n"
            f"Rubric for naturalness (1.0 to 5.0):\n{QA_NATURALNESS_RUBRIC}\n\n"
            "Evaluate:\n"
            "1. Did the assistant directly answer the user's question or guide them forward?\n"
            "2. Is the response consistent with the referenced model family?\n"
            "3. Are technical claims grounded without fabrication?\n"
            "4. If failure detected, assign failure_pattern to one of: 'generic_fallback', 'model_hallucination', 'unanswered_question', 'banned_boilerplate', or 'none'."
        )

        evidence = {
            "turn_id": turn_id,
            "user_message": user_msg,
            "assistant_message": bot_msg,
            "deterministic_flags": {
                "has_banned_phrases": has_banned,
                "has_leaked_tags": has_leaked_tags,
                "is_generic_fallback": is_generic_fallback,
            }
        }

        user_prompt = f"Evaluate quality, grounding, and tone of turn '{turn_id}'."

        score_res: TurnQAScoreOutput = self.runner.execute_step(
            step_name=f"qa_score_{turn_id}",
            system_instruction=system_instruction,
            user_prompt=user_prompt,
            evidence=evidence,
            output_schema=TurnQAScoreOutput,
            mock_response=mock_response,
        )

        # Merge deterministic failures if LLM missed them
        if has_banned and score_res.failure_pattern == "none":
            score_res.failure_pattern = "banned_boilerplate"
        if has_leaked_tags and score_res.failure_pattern == "none":
            score_res.failure_pattern = "leaked_template"
        if is_generic_fallback and score_res.failure_pattern == "none":
            score_res.failure_pattern = "generic_fallback"

        return score_res

    def draft_regression_tests(self, failed_turns: List[tuple[Dict[str, Any], TurnQAScoreOutput]]) -> Optional[Path]:
        """
        Auto-drafts a pytest regression test file in tests/proposed/
        """
        if not failed_turns:
            return None

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        test_file = PROPOSED_TESTS_DIR / f"test_nightly_regression_{timestamp}.py"

        content = [
            '"""',
            f'Auto-generated regression test suite from Nightly QA Job ({timestamp}).',
            '"""',
            'import pytest',
            'from workflow.orchestrator import run_turn',
            '',
        ]

        for i, (turn, score) in enumerate(failed_turns):
            user_msg = turn.get("user_message", "").replace('"', '\\"')
            content.extend([
                f'def test_qa_regression_turn_{i}():',
                f'    """Failure pattern: {score.failure_pattern} | Explanation: {score.explanation}"""',
                f'    user_input = "{user_msg}"',
                '    state, reply = run_turn(session_id="test_qa", message=user_input)',
                '    # Assert response does not repeat failure',
                '    assert reply is not None',
                '    assert not any(p in reply for p in ["Certainly!", "delighted to assist"])',
                '    assert "I apologize, but I am unable" not in reply',
                '',
            ])

        with open(test_file, "w", encoding="utf-8") as f:
            f.write("\n".join(content))

        logger.info(f"Auto-drafted regression tests at {test_file}")
        return test_file

    def run(self, limit: int = 20) -> Dict[str, Any]:
        turns = self.load_turns_to_evaluate(limit=limit)
        results: List[tuple[Dict[str, Any], TurnQAScoreOutput]] = []
        failure_clusters: Dict[str, int] = {}
        failed_turns: List[tuple[Dict[str, Any], TurnQAScoreOutput]] = []

        for turn in turns:
            try:
                score = self.evaluate_turn(turn)
                results.append((turn, score))
                if score.failure_pattern != "none" or score.naturalness < 3.0:
                    pattern = score.failure_pattern
                    failure_clusters[pattern] = failure_clusters.get(pattern, 0) + 1
                    failed_turns.append((turn, score))
            except Exception as e:
                logger.error(f"Error evaluating turn {turn.get('turn_id')}: {e}")

        self.runner.finalize()

        # Draft proposed tests if failures found
        drafted_test_path = self.draft_regression_tests(failed_turns)

        # Generate markdown report
        total = len(results)
        passed = total - len(failed_turns)
        pass_rate = (passed / total * 100.0) if total > 0 else 100.0
        avg_nat = sum(s.naturalness for _, s in results) / total if total > 0 else 5.0

        QA_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(QA_REPORT_PATH, "w", encoding="utf-8") as f:
            f.write("# Nightly Conversation Quality Assurance Report\n\n")
            f.write(f"- **Run ID:** `{self.runner.run_id}`\n")
            f.write(f"- **Total Turns Evaluated:** {total}\n")
            f.write(f"- **Pass Rate:** {pass_rate:.1f}%\n")
            f.write(f"- **Average Naturalness Score:** {avg_nat:.2f} / 5.0\n")
            if drafted_test_path:
                f.write(f"- **Auto-drafted Regression Test:** `{drafted_test_path}`\n\n")
            else:
                f.write("\n")

            f.write("## Failure Clusters (Top Patterns)\n\n")
            if failure_clusters:
                for pattern, count in sorted(failure_clusters.items(), key=lambda x: x[1], reverse=True)[:10]:
                    f.write(f"- **{pattern}**: {count} turns\n")
            else:
                f.write("No failure clusters detected. All turns passed threshold.\n")

            f.write("\n## Turn Evaluation Details\n\n")
            for turn, score in results[:20]:
                f.write(f"### Turn `{score.turn_id}`\n")
                f.write(f"- **User:** {turn.get('user_message', '')}\n")
                f.write(f"- **Score:** Nat: {score.naturalness}/5.0 | Grounding: {score.fact_grounding} | Consistency: {score.model_consistency}\n")
                f.write(f"- **Pattern:** `{score.failure_pattern}`\n")
                f.write(f"- **Explanation:** {score.explanation}\n\n")

        logger.info(f"Nightly QA report generated at {QA_REPORT_PATH}")
        return {
            "total": total,
            "pass_rate": pass_rate,
            "avg_naturalness": avg_nat,
            "failure_clusters": failure_clusters,
            "proposed_test": str(drafted_test_path) if drafted_test_path else None,
        }


def main():
    parser = argparse.ArgumentParser(description="Offline Nightly QA Evaluation Job")
    parser.add_argument("--limit", type=int, default=20, help="Max turns to evaluate")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    job = JobNightlyQA()
    summary = job.run(limit=args.limit)
    print(f"QA finished: {summary['total']} turns evaluated. Pass rate: {summary['pass_rate']:.1f}%")


if __name__ == "__main__":
    main()
