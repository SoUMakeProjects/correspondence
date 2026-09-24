"""Approved message envelopes select initial evidence, never an agent's next action."""

from app.fixture_data import SCENARIOS, load_fixture
from app.mail_contracts import MailTemplate

SERVICE_ADDRESS = "correspondence@servicing.example.com"

# The borrower's reply to the name-change information request (DEMO-01).
NAME_PROOF_BODY = (
    "Hello,\n\n"
    "Thank you for getting back to me. I've attached a certified copy of our marriage record "
    "from the Probate Court of Linden County. It shows my name change from Lauren E. Whitaker "
    "to Lauren E. Castellano.\n\n"
    "Please go ahead and update the name on loan 0099000001. Let me know if you need anything "
    "else.\n\n"
    "Thank you,\n"
    "Lauren Castellano\n"
    "(614) 555-0182"
)

# The borrower's reply to the EFT clarification request (DEMO-05), one per possible meaning.
EFT_REPLY_SIGNATURE = "Thanks,\nDanielle Foster\n(614) 555-0139"
EFT_REPLIES = {
    "outgoing_refund": (
        "Reply: send the escrow refund by EFT",
        "Hello,\n\n"
        "Thank you for the quick reply. I meant the escrow refund: I'd like the $486.27 surplus "
        "from my escrow statement deposited into my checking account instead of getting a paper "
        "check. My monthly payment can stay the way I pay it now.\n\n"
        "What do you need from me to set that up?\n\n" + EFT_REPLY_SIGNATURE,
    ),
    "incoming_payment": (
        "Reply: pay the mortgage by EFT each month",
        "Hello,\n\n"
        "Thank you for the quick reply. I meant my monthly mortgage payment: I'd like the new "
        "payment of $1,562.96 to come out of my checking account automatically each month "
        "instead of me mailing a check. The refund check is fine as it is.\n\n"
        "What do you need from me to set that up?\n\n" + EFT_REPLY_SIGNATURE,
    ),
    "heloc_draw": (
        "Reply: line-of-credit draw by EFT",
        "Hello,\n\n"
        "Thank you for the quick reply. I was asking about my home equity line of credit: I'd "
        "like to take a draw and have it sent to my checking account by EFT instead of a "
        "check.\n\n"
        "What do you need from me to set that up?\n\n" + EFT_REPLY_SIGNATURE,
    ),
}


def templates():
    result = []
    for scenario in SCENARIOS:
        fixture = load_fixture(scenario)
        sender = fixture.loan_context.get("authorized_recipient", fixture.borrower_email)
        envelope = dict(
            scenario=scenario,
            sender=sender,
            recipient=SERVICE_ADDRESS,
            subject=fixture.title,
        )
        # Existing schedules/servicing records are retrieved from OnBase/ILS;
        # only documents accompanying this correspondence are mail attachments.
        attachments = [
            {"key": d.key, "title": d.title}
            for d in fixture.documents
            if d.availability == "available" and scenario != "DEMO-02"
        ]
        result.append(
            MailTemplate(
                key=scenario,
                title=fixture.title,
                kind="initial",
                body=fixture.correspondence_text,
                attachments=attachments,
                **envelope,
            )
        )
        if scenario == "DEMO-01":
            result.append(
                MailTemplate(
                    key="name-proof",
                    title="Provide legal name-change document",
                    kind="reply",
                    body=NAME_PROOF_BODY,
                    attachments=[
                        {"key": "legal-document", "title": "Certified Copy of Marriage Record"}
                    ],
                    input_kind="name_legal_document",
                    **envelope,
                )
            )
        if scenario == "DEMO-02":
            result.append(
                MailTemplate(
                    key="schedule-copy",
                    title="Provide the requested schedule",
                    kind="reply",
                    body="I have attached the requested amortization schedule for this loan.",
                    attachments=[{"key": "amortization", "title": "Amortization schedule"}],
                    input_kind="amortization_document",
                    **envelope,
                )
            )
        if scenario == "DEMO-05":
            for intent, (title, body) in EFT_REPLIES.items():
                result.append(
                    MailTemplate(
                        key=f"eft-{intent}",
                        title=title,
                        kind="reply",
                        body=body,
                        attachments=[],
                        input_kind="eft_clarification",
                        eft_intent=intent,
                        **envelope,
                    )
                )
    return result
