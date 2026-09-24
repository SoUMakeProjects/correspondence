from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent import AgentWorker, request_stop, start
from app.agent_tools import artifacts
from app.automation import AutomationWorker
from app.azure_probe import last_check
from app.catalogs import install_catalogs
from app.config import Settings
from app.db import get_session, make_engine, make_sessions
from app.domain import DomainError
from app.mail_api import router as mail_router
from app.migrations import upgrade_database
from app.models import (
    ActionReceipt,
    AgentRun,
    CaseEvent,
    CorrespondenceCase,
    Evidence,
    FinalNote,
    IndexedPackage,
    Loan,
    OutboxEntry,
    SimulationInstance,
)
from app.phase2_api import router as phase2_router
from app.phase3_api import router as phase3_router
from app.phase4_api import router as phase4_router
from app.phase7_api import router as phase7_router
from app.phase8_api import router as phase8_router
from app.repository import case_read, create_case, require_case, update_case
from app.schemas import (
    ActionRead,
    ArtifactsRead,
    CaseCreate,
    CaseList,
    CasePatch,
    CaseRead,
    ConfigurationRead,
    ErrorResponse,
    EventPage,
    EventRead,
    EvidenceRead,
    HealthRead,
    ReviewCreate,
    ReviewRead,
    RunRead,
    RunStart,
    SimulationCreate,
    SimulationInspection,
    SimulationRead,
)
from app.workflow import review_response
from app.workspace_reset import router as workspace_reset_router

SessionDep = Annotated[Session, Depends(get_session)]


def create_app(settings: Settings | None = None, *, agent_model=None, start_worker=True) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        (settings.data_dir / "documents").mkdir(exist_ok=True)
        engine = make_engine(settings.database_url)
        worker = None
        automation = None
        try:
            upgrade_database(engine)
            application.state.sessions = make_sessions(engine)
            application.state.engine = engine
            with application.state.sessions() as session, session.begin():
                install_catalogs(session)
            worker = AgentWorker(settings, application.state.sessions, agent_model)
            application.state.agent_worker = worker
            automation = AutomationWorker(settings, application.state.sessions, worker)
            application.state.automation_worker = automation
            if start_worker:
                worker.launch()
                automation.launch()
            yield
        finally:
            if automation:
                automation.shutdown()
            if worker:
                worker.shutdown()
            engine.dispose()

    app = FastAPI(
        title="Correspondence Workspace API",
        version="0.9.0",
        description="Built-in mailbox, event-driven case automation, connected system workspaces and human review.",
        lifespan=lifespan,
        responses={code: {"model": ErrorResponse} for code in (404, 409, 422, 501)},
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(DomainError)
    async def domain_error(_request: Request, exc: DomainError):
        return JSONResponse(
            status_code=exc.status,
            content={"error": {"code": exc.code, "message": exc.message, "fields": []}},
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, exc: RequestValidationError):
        # Deliberately omit Pydantic's input/context, which may contain submitted secrets.
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "invalid_request",
                    "message": "Check the request fields and their types.",
                    "fields": [".".join(map(str, item["loc"])) for item in exc.errors()],
                }
            },
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error(_request: Request, _exc: IntegrityError):
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "record_conflict",
                    "message": "A record conflicts with existing data. Refresh before retrying.",
                    "fields": [],
                }
            },
        )

    @app.get("/api/health", response_model=HealthRead, tags=["System"])
    def health(session: SessionDep):
        revision = session.scalar(text("SELECT version_num FROM alembic_version"))
        return HealthRead(
            status="ok", database="connected", schema_revision=revision, version="0.9.0"
        )

    @app.get("/api/config", response_model=ConfigurationRead, tags=["System"])
    def configuration():
        probe = last_check(settings)
        return ConfigurationRead(
            phase=9,
            environment="simulation",
            model_provider="azure_openai",
            azure_configuration_complete=not settings.missing_azure_fields,
            missing_fields=settings.missing_azure_fields,
            model_connection_verified=bool(probe and probe.get("status") == "passed"),
            azure_last_live_check=probe["checked_at"]
            if probe and probe.get("status") == "passed"
            else None,
            model_calls_enabled=not settings.missing_azure_fields,
            live_test_opt_in=settings.azure_openai_live_tests_enabled,
            agent_available=not settings.missing_azure_fields,
            business_timezone="America/New_York",
            message="Azure agent runs are available when configured. All business actions use the local simulators.",
        )

    @app.post(
        "/api/simulations", response_model=SimulationRead, status_code=201, tags=["Simulation"]
    )
    def add_simulation(payload: SimulationCreate, session: SessionDep):
        with session.begin():
            instance = SimulationInstance(**payload.model_dump())
            session.add(instance)
            session.flush()
            result = SimulationRead.model_validate(instance)
        return result

    @app.get("/api/cases", response_model=CaseList, tags=["Cases"])
    def list_cases(
        session: SessionDep, limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0)
    ):
        rows = session.scalars(
            select(CorrespondenceCase)
            .order_by(CorrespondenceCase.original_received_at, CorrespondenceCase.id)
            .offset(offset)
            .limit(limit)
        ).all()
        return CaseList(
            items=[case_read(session, row) for row in rows],
            total=session.scalar(select(func.count()).select_from(CorrespondenceCase)),
        )

    @app.post("/api/cases", response_model=CaseRead, status_code=201, tags=["Cases"])
    def add_case(payload: CaseCreate, session: SessionDep):
        with session.begin():
            result = create_case(session, payload)
        return result

    @app.get("/api/cases/{case_id}", response_model=CaseRead, tags=["Cases"])
    def read_case(case_id: UUID, session: SessionDep):
        return case_read(session, require_case(session, str(case_id)))

    @app.patch("/api/cases/{case_id}", response_model=CaseRead, tags=["Cases"])
    def patch_case(case_id: UUID, payload: CasePatch, session: SessionDep):
        with session.begin():
            result = update_case(session, str(case_id), payload)
        return result

    @app.get("/api/cases/{case_id}/events", response_model=EventPage, tags=["Cases"])
    def read_events(
        case_id: UUID,
        session: SessionDep,
        after: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=200),
    ):
        require_case(session, str(case_id))
        events = session.scalars(
            select(CaseEvent)
            .where(CaseEvent.case_id == str(case_id), CaseEvent.sequence > after)
            .order_by(CaseEvent.sequence)
            .limit(limit)
        ).all()
        return EventPage(
            items=[EventRead.model_validate(row) for row in events],
            next_cursor=events[-1].sequence if events else after,
        )

    @app.get("/api/cases/{case_id}/evidence", response_model=list[EvidenceRead], tags=["Cases"])
    def read_evidence(case_id: UUID, session: SessionDep):
        require_case(session, str(case_id))
        return session.scalars(
            select(Evidence).where(Evidence.case_id == str(case_id)).order_by(Evidence.created_at)
        ).all()

    @app.get("/api/cases/{case_id}/actions", response_model=list[ActionRead], tags=["Cases"])
    def read_actions(case_id: UUID, session: SessionDep):
        require_case(session, str(case_id))
        return session.scalars(
            select(ActionReceipt)
            .where(ActionReceipt.case_id == str(case_id))
            .order_by(ActionReceipt.created_at)
        ).all()

    @app.get("/api/cases/{case_id}/runs", response_model=list[RunRead], tags=["Runs"])
    def list_runs(case_id: UUID, session: SessionDep):
        require_case(session, str(case_id))
        return session.scalars(
            select(AgentRun).where(AgentRun.case_id == str(case_id)).order_by(AgentRun.created_at)
        ).all()

    @app.get("/api/runs/{run_id}", response_model=RunRead, tags=["Runs"])
    def read_run(run_id: UUID, session: SessionDep):
        run = session.get(AgentRun, str(run_id))
        if not run:
            raise DomainError(404, "run_not_found", "This run was not found.")
        return run

    @app.post(
        "/api/cases/{case_id}/runs",
        response_model=RunRead,
        status_code=202,
        tags=["Runs"],
    )
    def start_run(case_id: UUID, payload: RunStart, session: SessionDep):
        worker = app.state.agent_worker
        run = start(session, settings, str(case_id), payload, worker.model.source)
        worker.wake.set()
        return run

    @app.post("/api/runs/{run_id}/stop", response_model=RunRead, tags=["Runs"])
    def stop_run(run_id: UUID, session: SessionDep):
        return request_stop(session, str(run_id))

    @app.get("/api/cases/{case_id}/artifacts", response_model=ArtifactsRead, tags=["Cases"])
    def read_artifacts(case_id: UUID, session: SessionDep):
        require_case(session, str(case_id))
        return artifacts(session, str(case_id))

    @app.post(
        "/api/cases/{case_id}/reviews",
        response_model=ReviewRead,
        status_code=201,
        tags=["Case workflow"],
    )
    def review(case_id: UUID, payload: ReviewCreate, session: SessionDep):
        return review_response(session, settings.data_dir, str(case_id), payload)

    @app.get(
        "/api/simulations/{simulation_id}", response_model=SimulationInspection, tags=["Simulation"]
    )
    def inspect_simulation(simulation_id: UUID, session: SessionDep):
        instance = session.get(SimulationInstance, str(simulation_id))
        if not instance:
            raise DomainError(
                404, "simulation_not_found", "This simulation instance was not found."
            )
        case_ids = select(CorrespondenceCase.id).where(
            CorrespondenceCase.simulation_id == instance.id
        )

        def count(model, field):
            return session.scalar(
                select(func.count()).select_from(model).where(field.in_(case_ids))
            )

        outbox = session.scalar(
            select(func.count())
            .select_from(OutboxEntry)
            .join(ActionReceipt, OutboxEntry.action_id == ActionReceipt.id)
            .where(ActionReceipt.case_id.in_(case_ids))
        )
        return SimulationInspection(
            simulation=SimulationRead.model_validate(instance),
            case_count=session.scalar(
                select(func.count())
                .select_from(CorrespondenceCase)
                .where(CorrespondenceCase.simulation_id == instance.id)
            ),
            loan_count=session.scalar(
                select(func.count()).select_from(Loan).where(Loan.simulation_id == instance.id)
            ),
            action_count=count(ActionReceipt, ActionReceipt.case_id),
            outbox_count=outbox,
            indexed_package_count=count(IndexedPackage, IndexedPackage.case_id),
            note_count=count(FinalNote, FinalNote.case_id),
            simulator_operations_available=True,
        )

    app.include_router(phase2_router)
    app.include_router(phase3_router)
    app.include_router(phase4_router)
    app.include_router(phase7_router)
    app.include_router(phase8_router)
    app.include_router(mail_router)
    app.include_router(workspace_reset_router)
    return app


app = create_app()
