"""Validated PDF/image uploads, immutable previews and case-scoped evidence."""

import hashlib
import re
from io import BytesIO
from typing import Annotated
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from PIL import Image
from pypdf import PdfReader
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import get_session
from app.domain import DomainError
from app.mail_contracts import MailAttachmentRead
from app.models import CorrespondenceCase, Evidence, Loan, MailAttachment, SimulationInstance
from app.simulators.artifacts import verified_file

MAX_BYTES = 5 * 1024 * 1024
MAX_PAGES = 50
TEXT_LIMIT = 12000
MEDIA_TYPES = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}
IMAGE_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "GIF": "image/gif", "WEBP": "image/webp"}
router = APIRouter(prefix="/mail")
SessionDep = Annotated[Session, Depends(get_session)]


def attachment_read(attachment):
    return {
        "id": attachment.id,
        "title": attachment.filename,
        "size_bytes": attachment.size_bytes,
        "page_count": attachment.page_count,
        "media_type": attachment.media_type,
    }


def parse_pdf(content):
    if not content.startswith(b"%PDF-"):
        raise DomainError(422, "pdf_required", "Only PDF attachments are allowed.")
    try:
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise DomainError(422, "pdf_encrypted", "Choose a PDF without password protection.")
        count = len(reader.pages)
        if not 1 <= count <= MAX_PAGES:
            raise DomainError(422, "pdf_page_limit", "A PDF must contain between 1 and 50 pages.")
        parts, remaining = [], TEXT_LIMIT
        for page in reader.pages:
            if remaining <= 0:
                break
            part = (page.extract_text() or "")[:remaining]
            parts.append(part)
            remaining -= len(part)
        return count, "\n".join(parts)[:TEXT_LIMIT]
    except DomainError:
        raise
    except Exception:
        raise DomainError(
            422, "invalid_pdf", "This file is not a readable PDF. Choose another file."
        ) from None


def validate_image(content, media_type):
    try:
        with Image.open(BytesIO(content)) as picture:
            if IMAGE_FORMATS.get(picture.format) != media_type:
                raise ValueError("Incorrect image type")
            frames = getattr(picture, "n_frames", 1)
            if picture.width * picture.height * frames > 25_000_000 or frames > 200:
                raise ValueError("Image dimensions too large")
            picture.verify()
        # Decode all frames as well: headers alone do not establish that a file is readable.
        with Image.open(BytesIO(content)) as picture:
            for frame in range(frames):
                picture.seek(frame)
                picture.load()
    except Exception:
        raise DomainError(
            422,
            "invalid_image",
            "This image is damaged or too large to display. Choose another image.",
        ) from None


@router.post("/attachments", response_model=MailAttachmentRead, status_code=201)
async def upload_attachment(
    request: Request,
    session: SessionDep,
    request_id: UUID,
    filename: str = Query(min_length=1, max_length=200),
):
    extension = filename.rsplit(".", 1)[-1].casefold()
    media_type = MEDIA_TYPES.get(extension)
    if (
        not media_type
        or re.search(r"[\\/:\x00-\x1f]", filename)
        or request.headers.get("content-type", "").split(";")[0].lower() != media_type
    ):
        raise DomainError(
            422, "attachment_type_required", "Choose a PDF or a PNG, JPEG, GIF or WebP image."
        )
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_BYTES:
            raise DomainError(
                413, "attachment_too_large", "Each attachment must be 5 MB or smaller."
            )
        content.extend(chunk)
    raw = bytes(content)
    if media_type == "application/pdf":
        pages, extracted = parse_pdf(raw)
    else:
        validate_image(raw, media_type)
        pages, extracted = 0, ""
    digest = hashlib.sha256(raw).hexdigest()
    session.execute(text("BEGIN IMMEDIATE"))
    prior = session.get(MailAttachment, str(request_id))
    if prior:
        if prior.content_sha256 != digest or prior.filename != filename:
            raise DomainError(409, "upload_id_reused", "This upload ID belongs to another file.")
        verified_file(request.app.state.settings.data_dir, prior.storage_key, prior.content_sha256)
        return attachment_read(prior)
    # A unique file per attempt avoids overwriting retained or interrupted uploads.
    from app.models import new_id

    key = f"mail-upload-{new_id()}.{extension}"
    path = request.app.state.settings.data_dir / "documents" / key
    written = False
    try:
        with path.open("xb") as output:
            written = True
            output.write(raw)
        row = MailAttachment(
            id=str(request_id),
            filename=filename,
            storage_key=key,
            content_sha256=digest,
            size_bytes=len(raw),
            page_count=pages,
            media_type=media_type,
            extracted_text=extracted,
        )
        session.add(row)
        session.commit()
        return attachment_read(row)
    except Exception:
        if written:
            path.unlink(missing_ok=True)
        raise


def upload_response(attachment, data_dir):
    path = verified_file(data_dir, attachment.storage_key, attachment.content_sha256)
    return FileResponse(
        path,
        media_type=attachment.media_type,
        filename=attachment.filename,
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get("/attachments/{attachment_id}/file")
def preview_upload(attachment_id: UUID, request: Request, session: SessionDep):
    row = session.get(MailAttachment, str(attachment_id))
    if not row:
        raise DomainError(404, "attachment_not_found", "This attachment is unavailable.")
    return upload_response(row, request.app.state.settings.data_dir)


def bind_uploads(session, message, identities, data_dir):
    if len(set(identities)) != len(identities):
        raise DomainError(422, "duplicate_attachment", "The same attachment was selected twice.")
    attached = []
    for identity in identities:
        row = session.get(MailAttachment, str(identity))
        if not row:
            raise DomainError(
                404, "attachment_not_found", "An attachment is unavailable. Add it again."
            )
        if row.message_id and row.message_id != message.id:
            raise DomainError(
                409,
                "attachment_already_sent",
                "This attachment belongs to another message. Add the file again.",
            )
        verified_file(data_dir, row.storage_key, row.content_sha256)
        row.message_id = message.id
        attached.append({**attachment_read(row), "upload_id": row.id, "key": f"upload:{row.id}"})
    message.attachments = [*message.attachments, *attached]


def uploaded_context(session, message_id):
    result = [
        {
            "filename": row.filename,
            "text": row.extracted_text,
            "page_count": row.page_count,
            "media_type": row.media_type,
        }
        for row in session.scalars(
            select(MailAttachment)
            .where(MailAttachment.message_id == message_id)
            .order_by(MailAttachment.created_at, MailAttachment.id)
        )
    ]
    # Edited prepared drafts still carry the selected physical files.
    from app.documents import library_document
    from app.mail_templates import templates
    from app.models import MailMessage

    message = session.get(MailMessage, message_id)
    template = next((t for t in templates() if t.key == message.template_key), None)
    if template:
        for attachment in message.attachments:
            if attachment.get("upload_id"):
                continue
            variant = "followup" if template.key == "name-proof" else "base"
            _, content = library_document(template.scenario, variant, attachment["key"])
            pages, extracted = parse_pdf(content)
            result.append(
                {
                    "filename": attachment["title"],
                    "text": extracted,
                    "page_count": pages,
                    "media_type": "application/pdf",
                }
            )
    return result


def import_prepared_mail(session, message, case_id, data_dir):
    """Retain selected files from edited initial drafts as unverified correspondence."""
    from app.documents import library_document
    from app.mail_templates import templates

    template = next((t for t in templates() if t.key == message.template_key), None)
    if not template:
        return
    case = session.get(CorrespondenceCase, case_id)
    loan = session.get(Loan, case.loan_id)
    for attachment in message.attachments:
        if attachment.get("upload_id"):
            continue
        identity = str(uuid5(NAMESPACE_URL, f"prepared-mail/{message.id}/{attachment['key']}"))
        if session.get(Evidence, identity):
            continue
        entry, content = library_document(template.scenario, "base", attachment["key"])
        pages, extracted = parse_pdf(content)
        key = f"mail-prepared-{identity}.pdf"
        path = data_dir / "documents" / key
        if not path.exists():
            with path.open("xb") as output:
                output.write(content)
        verified_file(data_dir, key, entry["sha256"])
        declared = set(re.findall(r"(?<!\d)\d{10}(?!\d)", extracted))
        session.add(
            Evidence(
                id=identity,
                case_id=case_id,
                title=attachment["title"],
                source="Email attachment",
                source_reference=f"mail:{message.id}/attachments/{attachment['key']}",
                storage_key=key,
                content_sha256=entry["sha256"],
                effective_at=message.created_at,
                details={
                    "key": attachment["key"],
                    "kind": "document",
                    "origin": "mail_upload",
                    "availability": "available",
                    "ccid": case.ccid,
                    "client_code": loan.client_code,
                    "loan_identifier": next(
                        (n for n in sorted(declared) if n != loan.loan_identifier),
                        loan.loan_identifier,
                    ),
                    "media_type": "application/pdf",
                    "page_count": pages,
                    "extracted_text": extracted,
                    "verification": "Unverified correspondence; content is not an authoritative servicing fact.",
                    "facts": {},
                },
            )
        )
        case.revision += 1
        case.content_revision = case.revision
    session.flush()


def import_uploads(session, message, case_id):
    case = session.get(CorrespondenceCase, case_id)
    loan = session.get(Loan, case.loan_id)
    simulation = session.get(SimulationInstance, case.simulation_id)
    created = False
    for row in session.scalars(
        select(MailAttachment).where(MailAttachment.message_id == message.id)
    ):
        evidence_id = str(uuid5(NAMESPACE_URL, f"mail-upload/{row.id}/{case_id}"))
        if session.get(Evidence, evidence_id):
            continue
        declared = sorted(set(re.findall(r"(?<!\d)\d{10}(?!\d)", row.extracted_text)))
        conflicting = next((value for value in declared if value != loan.loan_identifier), None)
        session.add(
            Evidence(
                id=evidence_id,
                case_id=case_id,
                title=row.filename,
                source="Email attachment",
                source_reference=f"mail:{message.id}/attachments/{row.id}",
                storage_key=row.storage_key,
                content_sha256=row.content_sha256,
                effective_at=simulation.evaluation_at,
                details={
                    "key": f"upload:{row.id}",
                    "kind": "document",
                    "origin": "mail_upload",
                    "availability": "available",
                    "ccid": case.ccid,
                    "client_code": loan.client_code,
                    "loan_identifier": conflicting or loan.loan_identifier,
                    "declared_loan_identifiers": declared,
                    "page_count": row.page_count,
                    "media_type": row.media_type,
                    "extracted_text": row.extracted_text,
                    "verification": "Unverified correspondence; content is not an authoritative servicing fact.",
                    "facts": {},
                },
            )
        )
        created = True
    if created:
        case.revision += 1
        case.content_revision = case.revision
        session.flush()
