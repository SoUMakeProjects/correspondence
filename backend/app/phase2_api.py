from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.catalogs import search_knowledge
from app.db import get_session
from app.documents import document_path
from app.domain import DomainError
from app.fixture_contracts import KnowledgeFixture, ScenarioKey, Variant
from app.fixture_data import scenario_catalog
from app.models import (
    ClientConfiguration,
    Concern,
    Evidence,
    SourceManifestEntry,
    SpecialistTask,
    TaxonomyEntry,
)
from app.repository import require_case
from app.schemas import CaseRead, Contract
from app.seeding import seed_scenario
from app.source_catalog import DATA_ROOT, read_json

router = APIRouter(prefix="/api", tags=["Synthetic data and references"])
SessionDep = Annotated[Session, Depends(get_session)]


class ScenarioRead(Contract):
    scenario_id: ScenarioKey
    version: str
    title: str
    family: str
    client_code: str
    variants: list[Variant]


class ScenarioLoad(Contract):
    request_id: UUID
    variant: Variant = "base"


class KnowledgeRead(KnowledgeFixture):
    id: UUID


class TaxonomyRead(Contract):
    id: str
    work_type: str
    class_name: str
    subclass: str
    source_reference: str


class TaxonomyPage(Contract):
    items: list[TaxonomyRead]
    total: int


class TaskRead(Contract):
    id: UUID
    case_id: UUID
    task_type: str
    owner: str
    status: str
    pending_reason: str | None
    request: dict
    result: dict | None


class ConcernRead(Contract):
    id: UUID
    case_id: UUID
    description: str
    disposition: str
    evidence_ids: list[UUID]


class ReferenceSummary(Contract):
    taxonomy_count: int
    knowledge_row_count: int
    statuses: dict[str, int]
    curated_item_count: int
    raw_response_text_exported: Literal[False]
    summary_reported_rows: int


@router.get("/scenarios", response_model=list[ScenarioRead])
def scenarios():
    return scenario_catalog()


@router.post("/scenarios/{scenario_id}/instances", response_model=CaseRead, status_code=201)
def load_scenario(
    scenario_id: ScenarioKey, payload: ScenarioLoad, request: Request, session: SessionDep
):
    return seed_scenario(
        session, request.app.state.settings, scenario_id, payload.variant, payload.request_id
    )


@router.get("/knowledge", response_model=list[KnowledgeRead])
def knowledge(
    session: SessionDep,
    scenario_id: ScenarioKey,
    client_code: Literal["DEMO-NORTH", "DEMO-HARBOR"],
    q: str = Query("", max_length=200),
    kind: Literal["guidance", "template", "disclosure"] | None = None,
):
    return search_knowledge(session, scenario_id, client_code, q, kind)


@router.get("/taxonomy", response_model=TaxonomyPage)
def taxonomy(
    session: SessionDep,
    q: str = Query("", max_length=200),
    work_type: str | None = None,
    class_name: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    filters = []
    if q:
        filters.append(
            or_(
                TaxonomyEntry.work_type.contains(q, autoescape=True),
                TaxonomyEntry.class_name.contains(q, autoescape=True),
                TaxonomyEntry.subclass.contains(q, autoescape=True),
            )
        )
    if work_type:
        filters.append(TaxonomyEntry.work_type == work_type)
    if class_name:
        filters.append(TaxonomyEntry.class_name == class_name)
    rows = session.scalars(
        select(TaxonomyEntry)
        .where(*filters)
        .order_by(TaxonomyEntry.work_type, TaxonomyEntry.class_name, TaxonomyEntry.subclass)
        .offset(offset)
        .limit(limit)
    ).all()
    return TaxonomyPage(
        items=[TaxonomyRead.model_validate(row) for row in rows],
        total=session.scalar(select(func.count()).select_from(TaxonomyEntry).where(*filters)),
    )


@router.get("/reference/summary", response_model=ReferenceSummary)
def reference_summary(session: SessionDep):
    report = read_json(DATA_ROOT / "knowledge/reconciliation.v1.json")
    return ReferenceSummary(
        taxonomy_count=session.scalar(select(func.count()).select_from(TaxonomyEntry)),
        knowledge_row_count=session.scalar(select(func.count()).select_from(SourceManifestEntry)),
        statuses=dict(
            session.execute(
                select(SourceManifestEntry.status, func.count()).group_by(
                    SourceManifestEntry.status
                )
            ).all()
        ),
        curated_item_count=report["curated_item_count"],
        raw_response_text_exported=False,
        summary_reported_rows=report["summary_reported_rows"],
    )


@router.get("/clients", response_model=list[dict])
def clients(session: SessionDep):
    return [
        {
            "code": row.code,
            "version": row.version,
            "display_name": row.display_name,
            "settings": row.settings,
        }
        for row in session.scalars(select(ClientConfiguration).order_by(ClientConfiguration.code))
    ]


@router.get("/cases/{case_id}/tasks", response_model=list[TaskRead])
def tasks(case_id: UUID, session: SessionDep):
    require_case(session, str(case_id))
    return session.scalars(
        select(SpecialistTask)
        .where(SpecialistTask.case_id == str(case_id))
        .order_by(SpecialistTask.id)
    ).all()


@router.get("/cases/{case_id}/concerns", response_model=list[ConcernRead])
def concerns(case_id: UUID, session: SessionDep):
    require_case(session, str(case_id))
    return session.scalars(
        select(Concern).where(Concern.case_id == str(case_id)).order_by(Concern.id)
    ).all()


@router.get("/cases/{case_id}/evidence/{evidence_id}/file", response_class=FileResponse)
def evidence_file(case_id: UUID, evidence_id: UUID, request: Request, session: SessionDep):
    require_case(session, str(case_id))
    evidence = session.get(Evidence, str(evidence_id))
    if evidence is None or evidence.case_id != str(case_id):
        raise DomainError(
            404, "evidence_not_found", "This evidence does not belong to the selected case."
        )
    path = document_path(request.app.state.settings.data_dir, evidence)
    return FileResponse(
        path,
        media_type=evidence.details.get("media_type", "application/pdf"),
        filename=evidence.title
        if evidence.details.get("origin") == "mail_upload"
        else f"{evidence.id}.pdf",
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff"},
    )
