"""
Offline Multi-Agent Jobs Package for Kepler Tech SalesAI.
Strictly executed offline (CLI / cron / event-driven); NEVER imported in the /api/chat path.
"""

from jobs.runner import JobRunner, JobStep, JobRunRecord

__all__ = ["JobRunner", "JobStep", "JobRunRecord"]
