from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import IndexedPackage, OutboxEntry, ResponseDraft
from app.simulators.artifacts import verify_package
from app.simulators.common import scope
from app.simulators.contracts import ToolDefinition, ToolRequest, ToolResult
from app.simulators.dispatcher import dispatch, registry

router = APIRouter(prefix="/api", tags=["Simulated systems"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/simulator/tools", response_model=list[ToolDefinition])
def tools_registry():
    return registry()


@router.post("/simulations/{simulation_id}/cases/{case_id}/tools", response_model=ToolResult)
def execute_tool(
    simulation_id: UUID, case_id: UUID, payload: ToolRequest, request: Request, session: SessionDep
):
    return dispatch(session, request.app.state.settings.data_dir, simulation_id, case_id, payload)


@router.get("/simulations/{simulation_id}/cases/{case_id}/packages/{package_id}/file")
def package_file(
    simulation_id: UUID,
    case_id: UUID,
    package_id: UUID,
    loan_identifier: str,
    client_code: str,
    request: Request,
    session: SessionDep,
):
    ctx = scope(
        session,
        request.app.state.settings.data_dir,
        simulation_id,
        case_id,
        loan_identifier,
        client_code,
    )
    package = ctx.scoped(IndexedPackage, package_id)
    draft = ctx.scoped(ResponseDraft, package.index_fields["draft_id"])
    outbox = ctx.scoped(OutboxEntry, package.index_fields["outbox_id"])
    path = verify_package(ctx.data_dir, package, outbox, ctx.case, ctx.loan, draft)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"{ctx.case.ccid}-response-package.pdf",
        content_disposition_type="inline",
    )
