from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.assessment import assess_case
from app.db import get_session
from app.domain import DomainError
from app.models import CaseEvent, RuleEvaluation
from app.repository import require_case
from app.response_validation import validate_completion, validate_response
from app.rule_contracts import (
    AssessmentCreate,
    AssessmentReport,
    DraftCandidate,
    SavedAssessment,
    ValidationReport,
)

router = APIRouter(prefix="/api", tags=["Business rules and validation"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/cases/{case_id}/assessment", response_model=AssessmentReport)
def current_assessment(case_id: UUID, request: Request, session: SessionDep):
    return assess_case(session, request.app.state.settings.data_dir, str(case_id))[0]


@router.post("/cases/{case_id}/assessments", response_model=SavedAssessment, status_code=201)
def save_assessment(
    case_id: UUID, payload: AssessmentCreate, request: Request, session: SessionDep
):
    with session.begin():
        # SQLite writer reservation serializes assessment capture with case edits.
        session.execute(text("BEGIN IMMEDIATE"))
        case = require_case(session, str(case_id))
        previous = session.scalar(
            select(RuleEvaluation).where(
                RuleEvaluation.case_id == case.id,
                RuleEvaluation.request_id == str(payload.request_id),
            )
        )
        if previous:
            if previous.case_revision != payload.expected_revision:
                raise DomainError(
                    409,
                    "request_id_reused",
                    "Use a new request ID for another assessment revision.",
                )
            return SavedAssessment(
                id=previous.id, created_at=previous.created_at, report=previous.report
            )
        if case.revision != payload.expected_revision:
            raise DomainError(
                409, "stale_revision", "Refresh the case before recording its assessment."
            )
        report, inputs = assess_case(session, request.app.state.settings.data_dir, case.id)
        saved = RuleEvaluation(
            case_id=case.id,
            request_id=str(payload.request_id),
            case_revision=case.revision,
            policy_version=report.policy_version,
            input_hash=report.input_hash,
            inputs=inputs,
            report=report.model_dump(mode="json"),
        )
        session.add(saved)
        session.flush()
        session.add(
            CaseEvent(
                case_id=case.id,
                kind="rules.assessed",
                actor="local_presenter",
                payload={
                    "assessment_id": saved.id,
                    "revision": case.revision,
                    "policy_version": saved.policy_version,
                    "input_hash": saved.input_hash,
                    "disposition": report.disposition,
                    "route": report.routing.route,
                },
            )
        )
        return SavedAssessment(id=saved.id, created_at=saved.created_at, report=report)


@router.get("/cases/{case_id}/assessments", response_model=list[SavedAssessment])
def assessment_history(case_id: UUID, session: SessionDep):
    require_case(session, str(case_id))
    return [
        SavedAssessment(id=row.id, created_at=row.created_at, report=row.report)
        for row in session.scalars(
            select(RuleEvaluation)
            .where(RuleEvaluation.case_id == str(case_id))
            .order_by(RuleEvaluation.created_at.desc(), RuleEvaluation.id.desc())
        )
    ]


@router.post("/cases/{case_id}/validate-response", response_model=ValidationReport)
def response_preflight(
    case_id: UUID, payload: DraftCandidate, request: Request, session: SessionDep
):
    return validate_response(session, request.app.state.settings.data_dir, str(case_id), payload)


@router.get("/cases/{case_id}/completion-check", response_model=ValidationReport)
def completion_preflight(case_id: UUID, request: Request, session: SessionDep):
    return validate_completion(session, request.app.state.settings.data_dir, str(case_id))
