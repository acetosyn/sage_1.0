"""Run with: python -m unittest discover -s tests -v."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from flask import Flask
from sqlalchemy.orm.attributes import set_committed_value

from core.datetime_utils import as_utc
from models import Department, FinancialRecord, Organization, PurchaseRequest, User
from packages.database import db
from services.briefing_service import build_daily_briefing
from services.management_service import executive_dashboard_context, management_anomaly_context
from services.operations_service import analytics_context


NOW = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)


class UTCNormalizationTests(unittest.TestCase):
    def test_naive_database_timestamp_is_utc(self):
        self.assertEqual(as_utc(NOW.replace(tzinfo=None)), NOW)

    def test_offsets_preserve_the_instant(self):
        midnight = NOW.replace(hour=0)
        for hours in (-5, 0, 1, 5.5):
            with self.subTest(hours=hours):
                offset_value = midnight.astimezone(timezone(timedelta(hours=hours)))
                self.assertEqual(as_utc(offset_value), midnight)
                self.assertIs(as_utc(offset_value).tzinfo, timezone.utc)


class DatabaseDatetimeTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", TESTING=True)
        db.init_app(self.app)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        organization = Organization(name="Test Business", slug="test-business", business_type="Retail")
        other = Organization(name="Other Business", slug="other-business", business_type="Retail")
        db.session.add_all([organization, other])
        db.session.flush()
        department = Department(organization_id=organization.id, name="Operations")
        db.session.add(department)
        db.session.flush()
        self.user = User(organization_id=organization.id, department_id=department.id,
                         first_name="Test", last_name="Owner", email="owner@example.test",
                         password_hash="unused-test-value", role="owner")
        db.session.add(self.user)
        db.session.flush()
        self.finance = []
        for index, (kind, amount, occurred_at) in enumerate([
            ("revenue", 200, NOW.replace(hour=0)),
            ("expense", 100, NOW),
            ("revenue", 70, NOW - timedelta(days=1)),
            ("expense", 40, NOW - timedelta(days=45)),
            ("expense", 30, NOW - timedelta(days=61)),
        ]):
            row = FinancialRecord(reference=f"TEST-FIN-{index}", organization_id=organization.id,
                                  department_id=department.id, record_type=kind,
                                  description="Regression fixture", amount=amount, occurred_at=occurred_at)
            db.session.add(row)
            self.finance.append(row)
        db.session.add(FinancialRecord(reference="OTHER-FIN", organization_id=other.id,
                                       record_type="expense", description="Other tenant", amount=9999,
                                       occurred_at=NOW))
        self.requests = []
        for index, created_at in enumerate([NOW.replace(hour=0), NOW - timedelta(days=1)]):
            row = PurchaseRequest(reference=f"TEST-REQ-{index}", organization_id=organization.id,
                                  department_id=department.id, requester_id=self.user.id,
                                  title="Regression request", status="approved", created_at=created_at,
                                  submitted_at=created_at, approved_at=created_at + timedelta(hours=2.5))
            db.session.add(row)
            self.requests.append(row)
        db.session.add(PurchaseRequest(reference="OTHER-REQ", organization_id=other.id,
                                       title="Other tenant", created_at=NOW))
        db.session.commit()
        # Force a real SQLite reload: DateTime(timezone=True) still comes back naive.
        db.session.expire_all()
        self.assertIsNone(self.finance[0].occurred_at.tzinfo)
        self.assertIsNone(self.requests[0].created_at.tzinfo)

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.context.pop()

    def assert_contexts(self):
        with patch("services.management_service.datetime", wraps=datetime) as clock:
            clock.now.return_value = NOW
            dashboard = executive_dashboard_context(self.user)
            alerts = management_anomaly_context(self.user)
        self.assertEqual(dashboard["today"]["income"], 200)
        self.assertEqual(dashboard["today"]["expenses"], 100)
        self.assertEqual(dashboard["today"]["new_requests"], 1)
        self.assertEqual(alerts["current_30_spend"], 100)
        self.assertEqual(alerts["previous_30_spend"], 40)
        self.assertTrue(any(row["kind"] == "spend_spike" for row in alerts["alerts"]))
        with patch("services.briefing_service.datetime", wraps=datetime) as clock:
            clock.now.return_value = NOW
            briefing = build_daily_briefing(self.user)
        request_slide = next(row for row in briefing["slides"] if row["route"] == "requests")
        self.assertTrue(request_slide["message"].startswith("1 new today"))
        self.assertEqual(analytics_context(self.user)["avg_approval_hours"], 2.5)

    def test_sqlite_timestamps_render_contexts_and_correct_totals(self):
        self.assert_contexts()

    def test_aware_timestamps_render_contexts_and_correct_totals(self):
        offset = timezone(timedelta(hours=-5))
        for row in self.finance:
            set_committed_value(row, "occurred_at", as_utc(row.occurred_at).astimezone(offset))
        for row in self.requests:
            for field in ("created_at", "submitted_at", "approved_at"):
                set_committed_value(row, field, as_utc(getattr(row, field)).astimezone(offset))
        self.assert_contexts()

    def test_mixed_naive_and_aware_timestamps_render_contexts(self):
        offset = timezone(timedelta(hours=1))
        for row in self.finance[::2]:
            set_committed_value(row, "occurred_at", as_utc(row.occurred_at).astimezone(offset))
        set_committed_value(self.requests[0], "created_at", as_utc(self.requests[0].created_at).astimezone(offset))
        # A just-approved request can have a naive submitted time and an aware approval time.
        set_committed_value(self.requests[0], "approved_at", as_utc(self.requests[0].approved_at).astimezone(offset))
        self.assert_contexts()


if __name__ == "__main__":
    unittest.main()
