import hashlib
import json
from datetime import timedelta

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.orm import Session

from app.db import utcnow
from app.domain import ActionStatus, CaseStatus, DomainError, RunStatus
from app.models import (
    ActionReceipt,
    AgentRun,
    CaseEvent,
    CorrespondenceCase,
    Loan,
    SimulationInstance,
    new_id,
)
from app.schemas import CaseCreate, CasePatch, CaseRead


def fingerprint(value: dict) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def require_case(session: Session, case_id: str) -> CorrespondenceCase:
    case = session.get(CorrespondenceCase, case_id)
    if case is None:
        raise DomainError(404, "case_not_found", "This correspondence case was not found.")
    return case


def case_read(session: Session, case: CorrespondenceCase) -> CaseRead:
    loan = session.get(Loan, case.loan_id)
    return CaseRead(
        **{
            name: getattr(case, name)
            for name in (
                "id",
                "simulation_id",
                "loan_id",
                "ccid",
                "subject",
                "correspondence_text",
                "family",
                "owner",
                "status",
                "original_received_at",
                "created_at",
                "updated_at",
                "revision",
                "classification",
                "content_revision",
                "routing",
                "pending_work",
            )
        },
        **{
            name: getattr(loan, name)
            for name in (
                "loan_identifier",
                "client_code",
                "borrower_display_name",
                "balance_minor",
                "currency",
            )
        },
    )


def create_case(session: Session, payload: CaseCreate) -> CaseRead:
    request_hash = fingerprint(payload.model_dump(mode="json"))
    existing = session.scalar(
        select(CorrespondenceCase).where(CorrespondenceCase.creation_key == str(payload.request_id))
    )
    if existing:
        if existing.creation_hash != request_hash:
            raise DomainError(
                409, "request_id_reused", "Use a new request ID for different case data."
            )
        return case_read(session, existing)

    if payload.simulation_id:
        simulation = session.get(SimulationInstance, str(payload.simulation_id))
        if not simulation:
            raise DomainError(
                404, "simulation_not_found", "This simulation instance was not found."
            )
    else:
        simulation = SimulationInstance(
            scenario_key="foundation", fixture_version="0", evaluation_at=utcnow()
        )
        session.add(simulation)
        session.flush()

    loan = session.scalar(
        select(Loan).where(
            Loan.simulation_id == simulation.id, Loan.loan_identifier == payload.loan_identifier
        )
    )
    loan_values = {
        name: getattr(payload, name)
        for name in (
            "loan_identifier",
            "client_code",
            "borrower_display_name",
            "balance_minor",
            "currency",
        )
    }
    if loan and any(getattr(loan, name) != value for name, value in loan_values.items()):
        raise DomainError(
            409,
            "loan_context_conflict",
            "The loan already has different context in this simulation.",
        )
    if not loan:
        loan = Loan(simulation_id=simulation.id, **loan_values)
        session.add(loan)
        session.flush()
    case = CorrespondenceCase(
        loan_id=loan.id,
        simulation_id=simulation.id,
        creation_key=str(payload.request_id),
        creation_hash=request_hash,
        ccid=payload.ccid,
        subject=payload.subject,
        correspondence_text=payload.correspondence_text,
        family=payload.family,
        owner=payload.owner,
        original_received_at=payload.original_received_at,
    )
    session.add(case)
    session.flush()
    session.add(
        CaseEvent(
            case_id=case.id,
            kind="case.created",
            actor="local_presenter",
            payload={"revision": 1, "status": "queued", "source": "foundation_sample"},
        )
    )
    session.flush()
    return case_read(session, case)


def update_case(session: Session, case_id: str, payload: CasePatch) -> CaseRead:
    case = require_case(session, case_id)
    action_key = f"foundation.case.update:{payload.mutation_id}"
    payload_hash = fingerprint(payload.model_dump(mode="json"))
    prior = session.scalar(
        select(ActionReceipt).where(
            ActionReceipt.case_id == case_id, ActionReceipt.idempotency_key == action_key
        )
    )
    if prior:
        if prior.payload_hash != payload_hash:
            raise DomainError(
                409, "mutation_id_reused", "A mutation ID cannot be reused for a different update."
            )
        return CaseRead.model_validate(prior.result["case"])
    if case.revision != payload.expected_revision:
        raise DomainError(
            409, "stale_revision", "This case changed. Refresh it before saving again."
        )

    changes = payload.model_dump(exclude_unset=True, exclude={"mutation_id", "expected_revision"})
    if case.status == "closed":
        raise DomainError(
            409, "case_closed", "A closed case cannot be edited through the foundation controls."
        )
    if session.scalar(
        select(ActionReceipt.id).where(
            ActionReceipt.case_id == case_id, ActionReceipt.status.in_(["uncertain", "in_progress"])
        )
    ):
        raise DomainError(
            409,
            "reconciliation_required",
            "Reconcile the outstanding simulated action before editing the case.",
        )
    target = changes.get("status")
    allowed = {
        CaseStatus.QUEUED: {CaseStatus.UNDER_REVIEW},
        CaseStatus.UNDER_REVIEW: {CaseStatus.QUEUED},
    }
    if target and target != case.status and target not in allowed.get(case.status, set()):
        raise DomainError(
            409,
            "transition_not_available",
            "Phase 1 supports queue/review transitions only. Completion controls arrive in later phases.",
        )
    before = {name: getattr(case, name) for name in changes}
    result = session.execute(
        update(CorrespondenceCase)
        .where(
            CorrespondenceCase.id == case_id,
            CorrespondenceCase.revision == payload.expected_revision,
        )
        .values(
            **changes,
            revision=payload.expected_revision + 1,
            content_revision=payload.expected_revision + 1,
            updated_at=utcnow(),
        )
    )
    if result.rowcount != 1:
        raise DomainError(
            409, "stale_revision", "This case changed. Refresh it before saving again."
        )
    session.refresh(case)
    saved = case_read(session, case)
    action = ActionReceipt(
        case_id=case_id,
        operation="foundation.case.update",
        idempotency_key=action_key,
        payload_hash=payload_hash,
        payload=payload.model_dump(mode="json"),
        status=ActionStatus.SIMULATED_COMPLETE,
        result={"case": saved.model_dump(mode="json")},
    )
    session.add(action)
    session.flush()
    session.add(
        CaseEvent(
            case_id=case_id,
            action_id=action.id,
            kind="case.updated",
            actor="local_presenter",
            payload={"before": before, "after": changes, "revision": saved.revision},
        )
    )
    session.flush()
    return saved


def claim_next_run(session: Session, worker_id: str, lease_seconds: int = 30) -> AgentRun | None:
    """Claim the local worker slot. Caller commits; recovered work needs reconciliation.

    Execution lives in AgentWorker; interrupted work must be inspected before replay.
    BEGIN IMMEDIATE serializes competing claims in SQLite across processes.
    """
    if not worker_id.strip() or lease_seconds < 1:
        raise ValueError("A worker identity and positive lease duration are required.")
    session.execute(text("BEGIN IMMEDIATE"))
    now = utcnow()
    active = session.scalar(
        select(func.count())
        .select_from(AgentRun)
        .where(AgentRun.status == RunStatus.RUNNING, AgentRun.lease_expires_at > now)
    )
    if active:
        return None
    run = session.scalar(
        select(AgentRun)
        .where(
            or_(
                AgentRun.status == RunStatus.QUEUED,
                (AgentRun.status == RunStatus.RUNNING)
                & or_(AgentRun.lease_expires_at <= now, AgentRun.lease_expires_at.is_(None)),
            )
        )
        .order_by(AgentRun.created_at, AgentRun.id)
        .limit(1)
    )
    if not run:
        return None
    recovering = run.status == RunStatus.RUNNING or run.checkpoint.get("recovery_pending", False)
    run.status = RunStatus.RUNNING
    run.lease_owner = worker_id
    run.lease_token = new_id()
    run.lease_expires_at = now + timedelta(seconds=lease_seconds)
    run.updated_at = now
    run.checkpoint = {**run.checkpoint, "reconciliation_required": recovering}
    session.flush()
    return run


def renew_lease(session: Session, run_id: str, token: str, lease_seconds: int = 30) -> bool:
    if lease_seconds < 1:
        raise ValueError("Lease duration must be positive.")
    now = utcnow()
    result = session.execute(
        update(AgentRun)
        .where(
            AgentRun.id == run_id,
            AgentRun.lease_token == token,
            AgentRun.status == RunStatus.RUNNING,
            AgentRun.lease_expires_at > now,
        )
        .values(lease_expires_at=now + timedelta(seconds=lease_seconds), updated_at=now)
    )
    return result.rowcount == 1
