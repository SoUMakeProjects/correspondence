import hashlib
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.documents import library_document
from app.domain import DomainError
from app.fixture_data import load_fixture
from app.models import (
    CaseEvent,
    ClientConfiguration,
    Concern,
    CorrespondenceCase,
    Evidence,
    Loan,
    SimulationInstance,
    SpecialistTask,
    new_id,
)
from app.repository import case_read, create_case, fingerprint
from app.schemas import CaseCreate, CaseRead


def seed_scenario(
    session: Session, settings: Settings, scenario_id: str, variant: str, request_id: UUID
) -> CaseRead:
    fixture = load_fixture(scenario_id, variant)
    documents = {
        doc.key: library_document(scenario_id, variant, doc.key) for doc in fixture.documents
    }
    seed_hash = fingerprint(
        {
            "fixture": fixture.model_dump(mode="json"),
            "variant": variant,
            "document_hashes": {key: entry[0]["sha256"] for key, entry in documents.items()},
        }
    )
    written: list[Path] = []
    try:
        with session.begin():
            prior = session.scalar(
                select(SimulationInstance).where(SimulationInstance.seed_key == str(request_id))
            )
            if prior:
                if prior.seed_hash != seed_hash:
                    raise DomainError(
                        409,
                        "seed_id_reused",
                        "Use a new request ID for a different fixture or variant.",
                    )
                case = session.scalar(
                    select(CorrespondenceCase).where(CorrespondenceCase.simulation_id == prior.id)
                )
                return case_read(session, case)
            client = session.get(ClientConfiguration, fixture.client_code)
            if client is None:
                raise DomainError(
                    409,
                    "catalog_not_loaded",
                    "Install the reference catalogs before loading scenarios.",
                )
            simulation = SimulationInstance(
                id=str(uuid5(NAMESPACE_URL, f"correspondence/simulation/{request_id}")),
                scenario_key=scenario_id,
                fixture_version=fixture.version,
                evaluation_at=fixture.evaluation_at,
                variant=variant,
                seed_key=str(request_id),
                seed_hash=seed_hash,
            )
            session.add(simulation)
            session.flush()
            created = create_case(
                session,
                CaseCreate(
                    request_id=request_id,
                    simulation_id=UUID(simulation.id),
                    loan_identifier=fixture.loan_identifier,
                    ccid=fixture.ccid,
                    client_code=fixture.client_code,
                    borrower_display_name=fixture.borrower_display_name,
                    balance_minor=fixture.balance_minor,
                    subject=fixture.title,
                    correspondence_text=fixture.correspondence_text,
                    family=fixture.family,
                    owner="Demo reviewer",
                    original_received_at=fixture.original_received_at,
                ),
            )
            case_id = str(created.id)
            loan = session.get(Loan, str(created.loan_id))
            loan.context = {
                **fixture.loan_context,
                "borrower_email": fixture.borrower_email,
                "synthetic": True,
                "client_configuration": {
                    "code": client.code,
                    "version": client.version,
                    "display_name": client.display_name,
                    **client.settings,
                },
            }
            case_event = session.scalar(select(CaseEvent).where(CaseEvent.case_id == case_id))
            case_event.payload = {
                **case_event.payload,
                "source": "versioned_fixture",
                "scenario_id": scenario_id,
                "fixture_version": fixture.version,
                "variant": variant,
            }
            context_evidence = Evidence(
                case_id=case_id,
                title="Synthetic servicing record",
                source="ILS simulator fixture",
                source_reference=f"fixture:v1/{scenario_id}/loan",
                synthetic=True,
                effective_at=fixture.evaluation_at,
                details={
                    "kind": "record",
                    "loan_identifier": fixture.loan_identifier,
                    "ccid": fixture.ccid,
                    "client_code": fixture.client_code,
                    "facts": loan.context,
                },
            )
            session.add(context_evidence)
            evidence_by_key = {}
            document_root = settings.data_dir / "documents"
            document_root.mkdir(parents=True, exist_ok=True)
            for document in fixture.documents:
                entry, content = documents[document.key]
                identity = new_id()
                storage_key = None
                if content is not None:
                    storage_key = f"{identity}.pdf"
                    path = document_root / storage_key
                    # A unique name and exclusive creation never overwrite an earlier run's file.
                    with path.open("xb") as output:
                        written.append(path)
                        output.write(content)
                evidence = Evidence(
                    id=identity,
                    case_id=case_id,
                    title=document.title,
                    source="OnBase simulator fixture",
                    source_reference=f"fixture:v1/{scenario_id}/{variant}/{document.key}",
                    effective_at=fixture.evaluation_at,
                    storage_key=storage_key,
                    content_sha256=hashlib.sha256(content).hexdigest() if content else None,
                    synthetic=True,
                    details={
                        "key": document.key,
                        "kind": document.kind,
                        "availability": document.availability,
                        "loan_identifier": document.declared_loan_identifier
                        or fixture.loan_identifier,
                        "ccid": "DEMO-CC-099"
                        if document.declared_loan_identifier
                        else fixture.ccid,
                        "client_code": fixture.client_code,
                        "facts": document.facts,
                    },
                )
                session.add(evidence)
                evidence_by_key[document.key] = identity
            session.flush()
            for description in fixture.concerns:
                session.add(
                    Concern(
                        case_id=case_id, description=description, evidence_ids=[context_evidence.id]
                    )
                )
            for task in fixture.tasks:
                session.add(
                    SpecialistTask(
                        case_id=case_id,
                        task_type=task.task_type,
                        owner=task.owner,
                        status=task.status,
                        pending_reason=task.pending_reason,
                        request={
                            **task.request,
                            "fixture_key": task.key,
                            "synthetic": True,
                            "loan_identifier": fixture.loan_identifier,
                            "client_code": fixture.client_code,
                            "evidence_ids": [evidence_by_key[key] for key in task.evidence_keys],
                        },
                        result=task.result,
                    )
                )
            session.flush()
            return case_read(session, session.get(CorrespondenceCase, case_id))
    except Exception:
        # Only files created by this transaction are removed; previous instances stay intact.
        for path in written:
            path.unlink(missing_ok=True)
        raise
