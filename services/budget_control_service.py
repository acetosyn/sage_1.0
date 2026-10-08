"""Automatic reservations and actual spend for approved purchase requests."""
from datetime import datetime, timezone
from decimal import Decimal
from models import BudgetAllocation, BudgetReservation
from packages.database import db


def sync_request_budget(request_row, actor, amount=None, budget_id=None, actual=None, release=False):
    if actor.organization_id != request_row.organization_id: raise PermissionError("Request is outside your organization.")
    reservation = BudgetReservation.query.filter_by(organization_id=actor.organization_id, request_id=request_row.id).first()
    today = datetime.now(timezone.utc).date()
    if reservation is None:
        query = BudgetAllocation.query.filter_by(organization_id=actor.organization_id, status="active")
        if budget_id: query = query.filter_by(id=budget_id)
        else: query = query.filter(BudgetAllocation.department_id == request_row.department_id, BudgetAllocation.period_start <= today, BudgetAllocation.period_end >= today)
        budgets = query.with_for_update().all()
        if budget_id and not budgets: raise ValueError("Choose an active budget from this organization.")
        # Multiple cost centres require an explicit choice; never allocate to an arbitrary budget.
        if len(budgets) != 1: return None
        budget = budgets[0]
        if budget.department_id not in (None, request_row.department_id): raise ValueError("Budget belongs to another department.")
        if release: return None
        reservation = BudgetReservation(organization_id=actor.organization_id, request_id=request_row.id, budget_id=budget.id, amount=Decimal("0"), actual_amount=Decimal("0"))
        db.session.add(reservation)
    budget = BudgetAllocation.query.filter_by(id=reservation.budget_id, organization_id=actor.organization_id).with_for_update().one()
    if release:
        if reservation.status == "committed": budget.committed_amount = max(Decimal("0"), Decimal(budget.committed_amount or 0) - Decimal(reservation.amount or 0))
        reservation.status = "released"
    elif actual is not None:
        if reservation.status == "committed": budget.committed_amount = max(Decimal("0"), Decimal(budget.committed_amount or 0) - Decimal(reservation.amount or 0))
        budget.actual_spend = Decimal(budget.actual_spend or 0) - Decimal(reservation.actual_amount or 0) + Decimal(str(actual))
        reservation.actual_amount, reservation.status = Decimal(str(actual)), "spent"
    elif reservation.status != "spent":
        value = Decimal(str(amount if amount is not None else request_row.estimated_total or 0))
        if not value.is_finite() or value < 0: raise ValueError("Enter a valid non-negative budget commitment.")
        budget.committed_amount = max(Decimal("0"), Decimal(budget.committed_amount or 0) - Decimal(reservation.amount or 0)) + value
        reservation.amount, reservation.status = value, "committed"
    return reservation
