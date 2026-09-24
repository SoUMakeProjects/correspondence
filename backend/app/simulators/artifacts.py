"""Immutable delivered files and combined PDF packages; no external storage."""

import hashlib
import json
from io import BytesIO
from xml.sax.saxutils import escape

from pypdf import PdfReader, PdfWriter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.domain import DomainError
from app.letter_emphasis import reportlab_markup


def digest(content):
    return hashlib.sha256(content).hexdigest()


def verified_file(data_dir, key, sha256, pdf=False):
    root = (data_dir / "documents").resolve()
    path = (root / key).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise DomainError(
            404, "artifact_missing", "The retained simulation artifact is unavailable."
        )
    content = path.read_bytes()
    if digest(content) != sha256:
        raise DomainError(
            409, "artifact_changed", "The retained artifact does not match its content hash."
        )
    if pdf:
        try:
            reader = PdfReader(BytesIO(content), strict=True)
            if not reader.pages or not any(p.extract_text().strip() for p in reader.pages):
                raise ValueError("Empty document")
        except Exception as exc:
            raise DomainError(
                422, "artifact_unreadable", "The retained PDF is not readable."
            ) from exc
    return path


def verify_sent_files(data_dir, sent):
    attachments = sent.get("attachments", [])
    if [a["evidence_id"] for a in attachments] != sent["attachment_ids"]:
        raise DomainError(
            422,
            "attachment_snapshot_mismatch",
            "Sent files do not match the recorded attachment selection.",
        )
    for attachment in attachments:
        media_type = attachment.get("media_type", "application/pdf")
        path = verified_file(
            data_dir,
            attachment["storage_key"],
            attachment["sha256"],
            pdf=media_type == "application/pdf",
        )
        if media_type.startswith("image/"):
            from app.mail_attachments import validate_image

            validate_image(path.read_bytes(), media_type)


def sent_matches(draft, case, loan, sent):
    expected = {
        "draft_id": draft.id,
        "draft_version": draft.version,
        "case_revision": draft.case_revision,
        "body": draft.body,
        "recipient": draft.recipient,
        "attachment_ids": draft.attachment_ids,
    }
    if any(sent.get(k) != v for k, v in expected.items()):
        return False
    if sent.get("schema_version") != 4:
        return False
    return (
        sent.get("client_code") == loan.client_code
        and sent.get("loan_identifier") == loan.loan_identifier
        and sent.get("ccid") == case.ccid
        and sent.get("simulation_id") == case.simulation_id
        and sent.get("sender") == loan.context.get("client_configuration", {}).get("sender_email")
        and sent.get("evidence_versions") == draft.evidence_versions
    )


def package_bytes(case, loan, sent, attachment_contents):
    buffer = BytesIO()
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(buffer, title="Synthetic correspondence package")
    story = [Paragraph("SIMULATED CORRESPONDENCE PACKAGE", styles["Title"])]
    for text in [
        f"Loan / Sherman ID: {loan.loan_identifier}",
        f"CCID: {case.ccid}",
        f"Client: {loan.client_code}",
        f"Sender: {sent['sender']}",
        f"Recipient: {sent['recipient']}",
        "Original correspondence",
        case.correspondence_text,
        "Sent response",
    ]:
        story.append(Paragraph(escape(text).replace("\n", "<br/>"), styles["BodyText"]))
        story.append(Spacer(1, 10))
    story.append(Paragraph(reportlab_markup(sent["body"]), styles["BodyText"]))
    story.append(Spacer(1, 10))
    document.build(story)
    writer = PdfWriter()
    writer.append(BytesIO(buffer.getvalue()))
    for attachment, content in zip(sent["attachments"], attachment_contents, strict=True):
        if attachment.get("media_type", "").startswith("image/"):
            from PIL import Image

            with Image.open(BytesIO(content)) as picture:
                converted = BytesIO()
                picture.convert("RGB").save(converted, format="PDF")
                content = converted.getvalue()
        writer.append(BytesIO(content))
    writer.add_metadata(
        {
            "/Title": "Synthetic correspondence package",
            "/Subject": f"{case.ccid} | {loan.loan_identifier}",
        }
    )
    result = BytesIO()
    writer.write(result)
    return result.getvalue(), len(writer.pages)


def verify_package(data_dir, package, outbox, case, loan, draft):
    path = verified_file(data_dir, package.storage_key, package.content_sha256)
    try:
        manifest = json.loads(path.read_bytes())
    except (ValueError, UnicodeError) as exc:
        raise DomainError(
            422, "archive_unreadable", "The indexed archive manifest cannot be read."
        ) from exc
    fields = package.index_fields
    if not {"pdf_storage_key", "pdf_sha256", "page_count"} <= fields.keys():
        raise DomainError(
            422,
            "package_pdf_missing",
            "A readable combined PDF and its recorded hash are required.",
        )
    expected = {
        "document_type": "Borrower Correspondence (Demo)",
        "correspondence_type": "INQ Email Reply",
        "sherman_id": loan.loan_identifier,
        "ccid": case.ccid,
        "case_id": case.id,
        "client_code": loan.client_code,
        "simulation_id": case.simulation_id,
        "draft_id": draft.id,
        "draft_version": draft.version,
        "outbox_id": outbox.id,
        "body_sha256": digest(draft.body.encode()),
    }
    if any(fields.get(k) != v for k, v in expected.items()) or manifest != {
        "sent_content": outbox.sent_content,
        "index_fields": fields,
    }:
        raise DomainError(
            422,
            "index_metadata_mismatch",
            "Index fields or archived content do not match the delivered response.",
        )
    verify_sent_files(data_dir, outbox.sent_content)
    pdf = verified_file(data_dir, fields["pdf_storage_key"], fields["pdf_sha256"], pdf=True)
    reader = PdfReader(pdf)
    if len(reader.pages) != fields["page_count"]:
        raise DomainError(
            422, "package_page_mismatch", "The indexed PDF page count differs from the manifest."
        )
    return pdf
