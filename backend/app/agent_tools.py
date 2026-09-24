"""Model decisions pass through the same scoped simulator as presenter actions."""

from sqlalchemy import select

from app.assessment import assess_case
from app.domain import DomainError
from app.models import (
    ActionReceipt,
    FinalNote,
    IndexedPackage,
    OutboxEntry,
    ResponseDraft,
    SpecialistHandoff,
)
from app.repository import require_case
from app.rule_contracts import DraftCandidate
from app.simulators.common import row_data, scope
from app.simulators.contracts import ToolRequest
from app.simulators.dispatcher import dispatch
from app.workflow import draft_state, latest_review


def artifacts(session, case_id):
    def rows(model):
        return [
            row_data(r)
            for r in session.scalars(
                select(model).where(model.case_id == case_id).order_by(model.created_at, model.id)
            )
        ]

    return {
        "drafts": rows(ResponseDraft),
        "outbox": [
            row_data(r)
            for r in session.scalars(
                select(OutboxEntry)
                .join(ActionReceipt, OutboxEntry.action_id == ActionReceipt.id)
                .where(ActionReceipt.case_id == case_id)
                .order_by(OutboxEntry.created_at)
            )
        ],
        "packages": rows(IndexedPackage),
        "notes": rows(FinalNote),
    }


def observe(session, data_dir, case_id):
    report, snapshot = assess_case(session, data_dir, case_id)
    # Enforce synthetic scope for reads as well as writes. No raw Office corpus is loaded.
    scope(
        session,
        data_dir,
        snapshot["case"]["simulation_id"],
        case_id,
        snapshot["loan"]["loan_identifier"],
        snapshot["loan"]["client_code"],
    )
    saved = artifacts(session, case_id)
    review = latest_review(session, case_id)
    handoffs = [
        row_data(h)
        for h in session.scalars(
            select(SpecialistHandoff).where(SpecialistHandoff.case_id == case_id)
        )
    ]
    plan_current = (
        snapshot["case"]["routing"] == report.routing.model_dump(mode="json")
        and snapshot["case"]["pending_work"]
        == [c.model_dump(mode="json") for c in report.concerns if c.disposition != "resolved"]
        and all(
            any(
                c["id"] == p.concern_id and c["disposition"] == p.disposition
                for c in snapshot["concerns"]
            )
            for p in report.concerns
        )
    )
    return {
        "case": snapshot["case"],
        "loan": snapshot["loan"],
        "client": snapshot["client"],
        "evidence": snapshot["evidence"],
        "tasks": snapshot["tasks"],
        "related_cases": snapshot["related_cases"],
        "plan_current": plan_current,
        "review": row_data(review) if review else None,
        "handoffs": [{**h, "current": h["input_hash"] == report.input_hash} for h in handoffs],
        "assessment": report.model_dump(mode="json"),
        "saved": {
            "drafts": [
                {
                    k: v
                    for k, v in draft_state(
                        session, data_dir, session.get(ResponseDraft, d["id"]), report
                    ).items()
                    # The server renders every letter from checked records; the model only
                    # chooses structure, so the long rendered body is not resent on each call.
                    if k not in {"candidate", "body"}
                }
                for d in saved["drafts"]
            ],
            "outbox": [
                {k: d[k] for k in ("id", "draft_id", "status", "delivery_reference")}
                for d in saved["outbox"]
            ],
            "packages": [
                {"id": d["id"], "draft_id": d["index_fields"]["draft_id"]}
                for d in saved["packages"]
            ],
            "notes": [{"id": d["id"], "details": d["details"]} for d in saved["notes"]],
        },
    }


def prepare_request(operation, arguments, observation, action_id):
    if observation is None:
        raise DomainError(409, "observation_required", "Inspect the case before using other tools.")
    case, loan, report = (observation[key] for key in ("case", "loan", "assessment"))
    command = {"operation": operation, **arguments}
    if operation not in {"knowledge.search", "onbase.retrieve", "ils.task"}:
        command.update(
            action_id=action_id,
            expected_revision=case["revision"],
            evidence_versions=report["evidence_versions"],
            input_hash=report["input_hash"],
        )
    if operation == "csp.prepare":
        client = observation["client"]
        candidate = DraftCandidate(
            **arguments,
            case_revision=case["content_revision"],
            version=max((d["version"] for d in observation["saved"]["drafts"]), default=0) + 1,
            client_code=loan["client_code"],
            client_version=client["version"],
            sender=client["settings"]["sender_email"],
            recipient=report["authorized_recipient"] or "",
            disclosure_ids=client["settings"]["disclosure_keys"],
            evidence_versions=report["evidence_versions"],
        )
        command = {key: value for key, value in command.items() if key not in arguments}
        command["candidate"] = candidate.model_dump(mode="json")
    return ToolRequest(
        loan_identifier=loan["loan_identifier"], client_code=loan["client_code"], command=command
    )


def execute(
    sessions, data_dir, case_id, operation, arguments, observation, action_id, run_id, token
):
    request = prepare_request(operation, arguments, observation, action_id)
    with sessions() as session:
        return dispatch(
            session,
            data_dir,
            observation["case"]["simulation_id"],
            case_id,
            request,
            run_id=run_id,
            lease_token=token,
        ).model_dump(mode="json")


def verified_outcome(session, data_dir, run, outcome):
    case = require_case(session, run.case_id)
    report, snapshot = assess_case(session, data_dir, run.case_id)
    pending = [c.model_dump(mode="json") for c in report.concerns if c.disposition != "resolved"]
    handoffs = list(
        session.scalars(
            select(SpecialistHandoff).where(
                SpecialistHandoff.case_id == case.id,
                SpecialistHandoff.input_hash == report.input_hash,
            )
        )
    )
    drafts = list(
        session.scalars(
            select(ResponseDraft)
            .where(ResponseDraft.case_id == case.id)
            .order_by(ResponseDraft.version.desc())
        )
    )
    latest = draft_state(session, data_dir, drafts[0], report) if drafts else None
    if outcome == "completed":
        from app.response_validation import validate_completion

        if case.status != "closed" or not validate_completion(session, data_dir, case.id).valid:
            raise DomainError(
                409,
                "completion_not_verified",
                "Execute and verify all completion actions before finishing.",
            )
    elif outcome == "waiting_for_review":
        if (
            not latest
            or not latest["current"]
            or latest["sent"]
            or latest["approved"]
            or not (latest["review_required"] or run.checkpoint.get("mode") == "review_required")
        ):
            raise DomainError(
                409, "review_not_required", "No review requirement has been recorded."
            )
    elif outcome == "transferred":
        if case.status != "transferred" or not any(h.status == "acknowledged" for h in handoffs):
            raise DomainError(
                409,
                "handoff_not_acknowledged",
                "Transfer requires acknowledgment of the current scoped handoff.",
            )
    elif (not pending and not report.findings) or case.pending_work != pending:
        raise DomainError(
            409, "pending_plan_required", "Record the actual pending concern plan before pausing."
        )
    if outcome == "waiting_for_input":
        if case.status == "transferred" and any(h.status == "acknowledged" for h in handoffs):
            raise DomainError(
                409,
                "handoff_acknowledged",
                "The current handoff is acknowledged and the case is transferred. Finish "
                "transferred.",
            )
        response_blocked = any("response" in f.blocks for f in report.findings)
        if (
            any(c["disposition"] == "pending_borrower" for c in pending)
            and not response_blocked
            and not (latest and latest["current"] and latest["sent"])
        ):
            raise DomainError(
                409,
                "information_request_not_sent",
                "Issue the supported information request before waiting for borrower input.",
            )
        if (
            snapshot["simulation"]["scenario_key"] == "DEMO-04"
            and not response_blocked
            and not session.scalar(
                select(OutboxEntry.id)
                .join(ResponseDraft, OutboxEntry.draft_id == ResponseDraft.id)
                .where(ResponseDraft.case_id == case.id, OutboxEntry.status == "sent")
            )
        ):
            # Counsel's dispute must be acknowledged in writing before the case waits on
            # Compliance; a recorded handoff alone leaves the representative without an answer.
            raise DomainError(
                409,
                "acknowledgment_not_sent",
                "Send the interim acknowledgment to the authorized representative before waiting.",
            )
        if report.routing.route == "Compliance" and not handoffs:
            raise DomainError(
                409,
                "handoff_required",
                "Record responsibility for the Compliance handoff before waiting.",
            )
        if (
            not pending
            and not handoffs
            and any(f.code == "classification_mapping_missing" for f in report.findings)
        ):
            # Every concern is answered but closure is blocked by a missing classification:
            # someone must own that decision, or the case is left without an owner.
            raise DomainError(
                409,
                "handoff_required",
                "Closure is blocked by a missing classification. Request the handoff before waiting.",
            )
    return {
        "case_status": case.status,
        "concerns": [c.model_dump(mode="json") for c in report.concerns],
        "pending_work": pending,
        "evidence_versions": report.evidence_versions,
        "handoffs": [row_data(h) for h in handoffs],
        "findings": [f.model_dump(mode="json") for f in report.findings],
    }
