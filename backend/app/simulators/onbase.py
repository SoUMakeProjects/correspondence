import json

from app.assessment import assess_case, check_evidence
from app.documents import document_path
from app.domain import DomainError
from app.models import Evidence, IndexedPackage, new_id
from app.simulators.artifacts import (
    digest,
    package_bytes,
    verified_file,
    verify_package,
    verify_sent_files,
)
from app.simulators.common import checked_draft, outbox_for, row_data


def read(ctx, operation, reference_id=None):
    if operation == "onbase.search":
        return {
            "evidence": [row_data(e) for e in ctx.rows(Evidence)],
            "packages": [row_data(p) for p in ctx.rows(IndexedPackage)],
        }
    if operation == "onbase.validate":
        report, _ = assess_case(ctx.session, ctx.data_dir, ctx.case.id)
        return {"attachments": [a.model_dump() for a in report.attachments]}
    evidence = ctx.session.get(Evidence, str(reference_id))
    if evidence and evidence.case_id == ctx.case.id:
        evidence = ctx.scoped(Evidence, reference_id)
        checked = check_evidence(ctx.data_dir, ctx.case, ctx.loan, evidence)
        if not checked.valid:
            raise DomainError(422, checked.code, checked.reason)
        if evidence.details.get("kind") != "record":
            document_path(ctx.data_dir, evidence)
        return {
            "evidence": row_data(evidence),
            "file_url": f"/api/cases/{ctx.case.id}/evidence/{evidence.id}/file"
            if evidence.storage_key
            else None,
        }
    package = ctx.scoped(IndexedPackage, reference_id)
    return {
        "package": row_data(package),
        "file_url": f"/api/simulations/{ctx.simulation.id}/cases/{ctx.case.id}/packages/{package.id}/file?loan_identifier={ctx.loan.loan_identifier}&client_code={ctx.loan.client_code}",
    }


def index(ctx, draft_id):
    draft = checked_draft(ctx, draft_id, require_approval=True)
    entry = outbox_for(ctx, draft.id)
    prior = next(
        (p for p in ctx.rows(IndexedPackage) if p.index_fields.get("outbox_id") == entry.id), None
    )
    if prior:
        verify_package(ctx.data_dir, prior, entry, ctx.case, ctx.loan, draft)
        return ctx.effect(prior, "package", {"package": row_data(prior), "reused": True})
    verify_sent_files(ctx.data_dir, entry.sent_content)
    contents = [
        verified_file(
            ctx.data_dir,
            a["storage_key"],
            a["sha256"],
            pdf=a.get("media_type", "application/pdf") == "application/pdf",
        ).read_bytes()
        for a in entry.sent_content["attachments"]
    ]
    pdf, pages = package_bytes(ctx.case, ctx.loan, entry.sent_content, contents)
    identity = new_id()
    pdf_key = ctx.write_file(f"package-{identity}.pdf", pdf)
    fields = {
        "document_type": "Borrower Correspondence (Demo)",
        "correspondence_type": "INQ Email Reply",
        "sherman_id": ctx.loan.loan_identifier,
        "ccid": ctx.case.ccid,
        "case_id": ctx.case.id,
        "client_code": ctx.loan.client_code,
        "simulation_id": ctx.simulation.id,
        "draft_id": draft.id,
        "draft_version": draft.version,
        "outbox_id": entry.id,
        "body_sha256": digest(draft.body.encode()),
        "pdf_storage_key": pdf_key,
        "pdf_sha256": digest(pdf),
        "page_count": pages,
        "mapping_version": "synthetic-index-v1",
    }
    manifest = json.dumps(
        {"sent_content": entry.sent_content, "index_fields": fields},
        ensure_ascii=False,
        sort_keys=True,
    ).encode()
    manifest_key = ctx.write_file(f"package-{identity}.json", manifest)
    package = IndexedPackage(
        id=identity,
        case_id=ctx.case.id,
        action_id=ctx.action.id,
        storage_key=manifest_key,
        content_sha256=digest(manifest),
        index_fields=fields,
    )
    ctx.session.add(package)
    return ctx.effect(package, "package")
