from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assessment import assess_case
from app.db import utcnow
from app.domain import DomainError
from app.models import (
    ActionReceipt,
    AgentRun,
    ClientConfiguration,
    CorrespondenceCase,
    Loan,
    OutboxEntry,
    ResponseDraft,
    ReviewDecision,
    SimulationInstance,
)
from app.repository import fingerprint, require_case
from app.response_validation import validate_response
from app.rule_contracts import DraftCandidate


def row_data(row):
    return {
        c.name: (
            getattr(row, c.name).isoformat()
            if hasattr(getattr(row, c.name), "isoformat")
            else getattr(row, c.name)
        )
        for c in row.__table__.columns
    }


@dataclass
class Context:
    session: Session
    data_dir: Path
    case: CorrespondenceCase
    loan: Loan
    simulation: SimulationInstance
    action: ActionReceipt | None = None
    written: list[Path] = field(default_factory=list)

    def scoped(self, model, identity):
        row = self.session.get(model, str(identity))
        owner = row.case_id if row and hasattr(row, "case_id") else None
        if row and isinstance(row, OutboxEntry):
            action = self.session.get(ActionReceipt, row.action_id)
            owner = action.case_id if action else None
        if not row or owner != self.case.id:
            raise DomainError(
                404, "reference_not_found", "No matching reference exists in this case."
            )
        return row

    def rows(self, model):
        return list(
            self.session.scalars(
                select(model)
                .where(model.case_id == self.case.id)
                .order_by(model.created_at, model.id)
            )
        )

    def bump(self, material=False):
        self.case.revision += 1
        self.case.updated_at = utcnow()
        if material:
            self.case.content_revision = self.case.revision

    def write_file(self, filename, content):
        root = (self.data_dir / "documents").resolve()
        root.mkdir(parents=True, exist_ok=True)
        path = (root / filename).resolve()
        if not path.is_relative_to(root):
            raise DomainError(
                422, "invalid_storage_path", "The artifact path leaves the simulation."
            )
        with path.open("xb") as output:
            self.written.append(path)
            output.write(content)
        return filename

    def effect(self, row, kind, data=None):
        self.session.flush()
        return {
            "resource": {"kind": kind, "id": row.id},
            "data": data or {kind: row_data(row)},
            "effect_hash": fingerprint(row_data(row)),
        }


def scope(session, data_dir, simulation_id, case_id, loan_identifier, client_code):
    case = require_case(session, str(case_id))
    loan = session.get(Loan, case.loan_id)
    if (
        case.simulation_id != str(simulation_id)
        or loan.loan_identifier != loan_identifier
        or loan.client_code != client_code
    ):
        raise DomainError(
            404,
            "scope_not_found",
            "No matching case exists in this simulation, loan and client scope.",
        )
    client = session.get(ClientConfiguration, client_code)
    if (
        not loan.context.get("synthetic")
        or not client
        or client.settings.get("synthetic") is not True
    ):
        raise DomainError(
            422,
            "synthetic_scope_required",
            "Simulators accept only the configured synthetic demo records.",
        )
    return Context(
        session, data_dir, case, loan, session.get(SimulationInstance, case.simulation_id)
    )


def checked_draft(ctx, identity, require_approval=False):
    draft = ctx.scoped(ResponseDraft, identity)
    latest = ctx.session.scalar(
        select(ResponseDraft.id)
        .where(ResponseDraft.case_id == ctx.case.id)
        .order_by(ResponseDraft.version.desc())
    )
    if latest != draft.id:
        raise DomainError(409, "stale_draft", "Use the latest prepared response version.")
    candidate = DraftCandidate.model_validate(draft.validation.get("candidate", {}))
    report = validate_response(ctx.session, ctx.data_dir, ctx.case.id, candidate)
    assessment, _ = assess_case(ctx.session, ctx.data_dir, ctx.case.id)
    if not report.valid:
        raise DomainError(422, "response_invalid", "; ".join(f.message for f in report.findings))
    if (
        draft.version != candidate.version
        or draft.case_revision != candidate.case_revision
        or draft.body != report.rendered_body
        or draft.recipient != candidate.recipient
        or draft.attachment_ids != candidate.attachment_ids
        or draft.evidence_versions != candidate.evidence_versions
        or draft.response_type != candidate.response_type
        or draft.disclosure_ids != candidate.disclosure_ids
        or draft.validation.get("input_hash") != assessment.input_hash
    ):
        raise DomainError(
            409, "stale_draft", "The response or its material inputs changed after preparation."
        )
    if require_approval:
        run = (
            ctx.session.get(AgentRun, ctx.action.run_id)
            if ctx.action and ctx.action.run_id
            else None
        )
        run_requires_review = bool(run and run.checkpoint.get("mode") == "review_required")
        latest_review = ctx.session.scalar(
            select(ReviewDecision)
            .where(ReviewDecision.case_id == ctx.case.id)
            .order_by(ReviewDecision.created_at.desc(), ReviewDecision.id.desc())
        )
        if (
            assessment.review_required
            or run_requires_review
            or draft.validation.get("review_required")
            or latest_review
        ) and (
            not latest_review
            or latest_review.decision != "approve"
            or latest_review.draft_id != draft.id
            or latest_review.draft_version != draft.version
            or latest_review.case_revision != ctx.case.content_revision
            or latest_review.content_hash
            != fingerprint(
                {
                    "candidate": candidate.model_dump(mode="json"),
                    "input_hash": assessment.input_hash,
                }
            )
        ):
            raise DomainError(
                409,
                "review_required",
                "Current approval is required for this response and evidence version.",
            )
    return draft


def outbox_for(ctx, draft_id):
    entry = ctx.session.scalar(select(OutboxEntry).where(OutboxEntry.draft_id == str(draft_id)))
    if not entry:
        raise DomainError(
            409, "delivery_missing", "A confirmed simulated delivery is required first."
        )
    entry = ctx.scoped(OutboxEntry, entry.id)
    receipt = ctx.scoped(ActionReceipt, entry.action_id)
    if entry.status != "sent" or receipt.status != "simulated_complete":
        raise DomainError(409, "delivery_unconfirmed", "Reconcile the send before proceeding.")
    return entry
