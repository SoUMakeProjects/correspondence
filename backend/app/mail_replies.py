"""Validate edited reply meaning and identity before continuing an existing case."""

from app.agent_model import ModelError
from app.custom_intake import REQUESTS, match_record, validate_classification
from app.domain import DomainError
from app.mail_attachments import uploaded_context


def reply_intent(worker, message, template, loan):
    authorized = loan.context.get("authorized_recipient", loan.context.get("borrower_email"))
    if message.sender.casefold() != str(authorized).casefold():
        raise DomainError(
            409,
            "mail_sender_review",
            "Verify the sender's authority for this loan before processing.",
        )
    if message.body == template.body and message.subject == "Re: " + template.subject:
        return template.eft_intent
    with worker.sessions() as session:
        attachments = uploaded_context(session, message.id)
    model = worker.agent_worker.model
    if model.source == "live_azure" and worker.settings.missing_azure_fields:
        raise DomainError(
            409, "azure_not_configured", "Message saved. Configure Azure to classify this reply."
        )
    try:
        choice = model.classify(
            {
                "sender": message.sender,
                "subject": message.subject,
                "body": message.body,
                "attachments": attachments,
            },
            worker.settings.azure_openai_timeout_seconds,
        )
        classification = validate_classification(choice, message, attachments)
    except (ModelError, AttributeError):
        raise DomainError(
            409,
            "mail_reply_review",
            "This reply could not be classified. Review the reply before continuing.",
        ) from None
    record = match_record(message, classification, attachments=attachments)
    if record.loan_identifier != loan.loan_identifier:
        raise DomainError(
            409,
            "mail_identity_review",
            "The reply refers to a different loan. Send a new request for that loan.",
        )
    if not classification.certain or REQUESTS[classification.request_type][0] != template.scenario:
        raise DomainError(
            409,
            "mail_reply_review",
            "The reply changes the request or needs clarification. Send a new message for a different request.",
        )
    if (
        template.scenario == "DEMO-01"
        and classification.requested_name
        and classification.requested_name != loan.context.get("requested_legal_name")
    ):
        raise DomainError(
            409,
            "mail_reply_review",
            "The requested name differs from the existing case. Review the request and legal document before continuing.",
        )
    if template.scenario == "DEMO-05" and not classification.eft_intent:
        raise DomainError(
            409, "mail_reply_review", "Clarify the payment purpose before continuing."
        )
    return classification.eft_intent if template.scenario == "DEMO-05" else template.eft_intent
