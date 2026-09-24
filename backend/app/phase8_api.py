from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.recovery import RestoreStatus, check_actions, inspect_recovery, restore_status
from app.run_reporting import evidence_export, run_summary
from app.schemas import Contract
from app.workflow_contracts import PresenterMutation

router = APIRouter(prefix="/api", tags=["Recovery and run evidence"])
SessionDep = Annotated[Session, Depends(get_session)]


class RecoveryRead(Contract):
    case_id: str
    revision: int
    blocked: bool
    actions: list[dict]


class SummaryRead(Contract):
    run_id: str
    case_id: str
    scenario: str
    status: str
    current_case_status: str
    resumed_from: str | None
    reason: str | None
    elapsed_seconds: float
    elapsed_includes_recovery_waits: bool
    model_calls: int
    reported_tokens: int
    usage_complete: bool
    source: str
    completed_actions: int
    failed_actions: int
    reconciled_actions: int
    case_interventions_through_run: int
    interventions: list[dict]
    recovery_count: int
    pending_concerns: int
    actions: list[dict]
    recovery: RecoveryRead
    measurement_scope: str


@router.get("/cases/{case_id}/recovery", response_model=RecoveryRead)
def recovery_status(case_id: UUID, request: Request, session: SessionDep):
    return inspect_recovery(session, request.app.state.settings.data_dir, str(case_id))


@router.post("/cases/{case_id}/recovery/check", response_model=dict)
def reconcile_actions(
    case_id: UUID, payload: PresenterMutation, request: Request, session: SessionDep
):
    return check_actions(session, request.app.state.settings.data_dir, str(case_id), payload)


@router.post("/cases/{case_id}/recovery/restore-status", response_model=dict)
def restore_simulator_status(
    case_id: UUID, payload: RestoreStatus, request: Request, session: SessionDep
):
    return restore_status(session, request.app.state.settings.data_dir, str(case_id), payload)


@router.get("/runs/{run_id}/summary", response_model=SummaryRead)
def summarize_run(run_id: UUID, request: Request, session: SessionDep):
    return run_summary(session, request.app.state.settings.data_dir, str(run_id))


@router.get("/runs/{run_id}/export", response_class=JSONResponse)
def export_run(run_id: UUID, request: Request, session: SessionDep):
    return JSONResponse(
        evidence_export(session, request.app.state.settings.data_dir, str(run_id)),
        headers={"Content-Disposition": f'attachment; filename="demo-run-{run_id}.json"'},
    )
