"""Unit tests for scheduler market session and after-hours execution controls."""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

from earnings_engine.config import Settings
from earnings_engine.data.automation_schedules import (
    init_automation_schedules,
    get_all_schedules,
    get_schedule,
    create_schedule,
    update_schedule,
    delete_schedule,
)
from earnings_engine.data.scheduler_engine import SchedulerEngine
from earnings_engine.data.migrations import apply_migrations


class TestSchedulerMarketHours(unittest.TestCase):
    def setUp(self):
        self.settings = Settings()
        apply_migrations(self.settings)
        init_automation_schedules(self.settings)

    def test_create_and_update_schedule_market_session(self):
        job_id = "test_market_hours_job"
        delete_schedule(job_id, self.settings)

        # 1. Create with market_hours_only
        job_data = {
            "job_id": job_id,
            "job_name": "Test Market Hours Job",
            "category": "Test",
            "interval_seconds": 60,
            "market_session": "market_hours_only",
            "run_after_hours": False,
            "is_enabled": True,
        }
        created = create_schedule(job_data, self.settings)
        self.assertEqual(created.get("job_id"), job_id)
        self.assertEqual(created.get("market_session"), "market_hours_only")
        self.assertEqual(created.get("run_after_hours"), False)

        # 2. Update to after_hours_only
        updated = update_schedule(job_id, {"market_session": "after_hours_only"}, self.settings)
        self.assertEqual(updated.get("market_session"), "after_hours_only")
        self.assertEqual(updated.get("run_after_hours"), True)

        # 3. Update to all (24/7)
        updated_247 = update_schedule(job_id, {"market_session": "all"}, self.settings)
        self.assertEqual(updated_247.get("market_session"), "all")
        self.assertEqual(updated_247.get("run_after_hours"), True)

        # Clean up
        delete_schedule(job_id, self.settings)

    @patch("earnings_engine.data.market_pulse.is_market_open")
    def test_scheduler_engine_market_open_filtering(self, mock_is_market_open):
        engine = SchedulerEngine()
        engine.dispatch_job = MagicMock()

        # Mock market as CLOSED (False)
        mock_is_market_open.return_value = False

        # Create two test jobs, one market_hours_only and one all
        now_dt = datetime.now(timezone.utc)
        past_iso = (now_dt - timedelta(seconds=10)).isoformat()

        job_mh = "test_eval_mh_only"
        job_all = "test_eval_all_session"

        create_schedule({
            "job_id": job_mh,
            "job_name": "MH Only",
            "market_session": "market_hours_only",
            "run_after_hours": False,
            "interval_seconds": 30,
            "is_enabled": True,
        }, self.settings)

        create_schedule({
            "job_id": job_all,
            "job_name": "All Session",
            "market_session": "all",
            "run_after_hours": True,
            "interval_seconds": 30,
            "is_enabled": True,
        }, self.settings)

        # Force next_run_at to past so they are due
        from earnings_engine.data.db import get_db_connection
        conn = get_db_connection(self.settings)
        conn.execute("UPDATE automation_schedules SET next_run_at = ? WHERE job_id IN (?, ?)", (past_iso, job_mh, job_all))
        if hasattr(conn, "commit"):
            conn.commit()

        # Run _evaluate_due_jobs synchronously with market closed
        import asyncio
        asyncio.run(engine._evaluate_due_jobs())

        # When market is closed: job_mh must NOT be dispatched, job_all MUST be dispatched
        dispatched_jobs = [call[0][0] for call in engine.dispatch_job.call_args_list]
        self.assertNotIn(job_mh, dispatched_jobs, "Market hours only job should NOT run when market is closed")
        self.assertIn(job_all, dispatched_jobs, "24/7 job should run even when market is closed")

        # Now test when market is OPEN (True)
        mock_is_market_open.return_value = True
        engine.dispatch_job.reset_mock()

        asyncio.run(engine._evaluate_due_jobs())
        dispatched_jobs_open = [call[0][0] for call in engine.dispatch_job.call_args_list]
        self.assertIn(job_mh, dispatched_jobs_open, "Market hours only job MUST run when market is open")
        self.assertIn(job_all, dispatched_jobs_open, "24/7 job MUST run when market is open")

        # Clean up
        delete_schedule(job_mh, self.settings)
        delete_schedule(job_all, self.settings)


if __name__ == "__main__":
    unittest.main()
