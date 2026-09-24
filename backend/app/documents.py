"""Deterministic synthetic attachments and case-scoped document access."""

import hashlib
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.domain import DomainError
from app.fixture_data import SCENARIOS, load_fixture, variants_for
from app.models import Evidence
from app.source_catalog import DATA_ROOT, read_json, write_json


def schedule_entries(facts: dict) -> list[dict]:
    """Exact-cent schedule. A contractual payment is used when the facts supply one."""
    balance = Decimal(facts["opening_principal_minor"])
    rate = Decimal(facts["annual_rate_basis_points"]) / 10000 / 12
    months = facts["remaining_payments"]
    payment = (
        Decimal(facts["principal_interest_minor"])
        if facts.get("principal_interest_minor")
        else (balance * rate / (1 - (1 + rate) ** -months)).quantize(Decimal(1), ROUND_HALF_UP)
    )
    year, month, _ = map(int, facts["first_payment_date"].split("-"))
    number = facts.get("first_payment_number", 1)
    entries = []
    for index in range(months):
        interest = (balance * rate).quantize(Decimal(1), ROUND_HALF_UP)
        paid = balance + interest if index == months - 1 else payment
        principal = paid - interest
        balance -= principal
        month_index = year * 12 + month - 1 + index
        entries.append(
            {
                "number": number + index,
                "year": month_index // 12,
                "month": month_index % 12 + 1,
                "payment": paid,
                "interest": interest,
                "principal": principal,
                "balance": balance,
            }
        )
    return entries


def money(minor) -> str:
    return f"${Decimal(minor) / 100:,.2f}"


def amortization_rows(facts: dict) -> list[list[str]]:
    rows = [["Due date", "Payment", "Interest", "Principal", "Balance"]]
    for row in schedule_entries(facts):
        rows.append(
            [
                f"{row['year']}-{row['month']:02}-01",
                *[money(row[k]) for k in ("payment", "interest", "principal", "balance")],
            ]
        )
    return rows


def long_date(value: str) -> str:
    year, month, day = map(int, value[:10].split("-"))
    return f"{MONTHS[month - 1]} {day}, {year}"


MONTHS = (
    "January February March April May June July August September October November December"
).split()

# Alternate identity printed on the deliberately mismatched wrong-loan variant.
WRONG_LOAN_PARTY = {
    "borrower": "Patricia L. Owens",
    "mailing_address": "62 Alder Court, Summit, NJ 07901",
    "property_address": "62 Alder Court, Summit, NJ 07901",
}


def client_settings(code: str) -> dict:
    for row in read_json(DATA_ROOT / "fixtures/v1/clients.json"):
        if row["code"] == code:
            return {"display_name": row["display_name"], **row["settings"]}
    return {"display_name": code}


class _NumberedCanvas:
    """Factory for a canvas that knows the total page count ("Page x of y")."""

    def __new__(cls, footer_text):
        from reportlab.pdfgen.canvas import Canvas

        class NumberedCanvas(Canvas):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._pages = []

            def showPage(self):
                self._pages.append(dict(self.__dict__))
                self._startPage()

            def save(self):
                total = len(self._pages)
                for state in self._pages:
                    self.__dict__.update(state)
                    self.saveState()
                    self.setFont("Helvetica", 7.5)
                    self.setFillColor(colors.HexColor("#5b6770"))
                    self.drawString(48, 28, footer_text)
                    self.drawRightString(564, 28, f"Page {self._pageNumber} of {total}")
                    self.restoreState()
                    super().showPage()
                super().save()

        return NumberedCanvas


def render_amortization(fixture, document, variant: str) -> bytes:
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import CondPageBreak, KeepTogether

    facts, context = document.facts, fixture.loan_context
    loan = document.declared_loan_identifier or fixture.loan_identifier
    wrong_loan = loan != fixture.loan_identifier
    party = (
        WRONG_LOAN_PARTY
        if wrong_loan
        else {
            "borrower": fixture.borrower_display_name,
            "mailing_address": context.get("mailing_address", ""),
            "property_address": context.get("property_address", ""),
        }
    )
    client = client_settings(fixture.client_code)
    entries = schedule_entries(facts)
    ink, muted, rule, band = (
        colors.HexColor("#14213d"),
        colors.HexColor("#5b6770"),
        colors.HexColor("#c9d3dc"),
        colors.HexColor("#eef2f6"),
    )
    base = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=base["Normal"], fontSize=9, leading=13, textColor=ink)
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=11, textColor=muted)
    brand = ParagraphStyle("brand", parent=body, fontName="Helvetica-Bold", fontSize=15, leading=18)
    heading = ParagraphStyle(
        "heading", parent=body, fontName="Helvetica-Bold", fontSize=13, leading=17, spaceAfter=2
    )
    section = ParagraphStyle(
        "section",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=14,
        spaceBefore=10,
        spaceAfter=4,
    )
    right = ParagraphStyle("right", parent=small, alignment=TA_RIGHT)

    buffer = BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=(612, 792),
        rightMargin=48,
        leftMargin=48,
        topMargin=44,
        bottomMargin=52,
        invariant=1,
        title=f"{document.title} - Loan {loan}",
        author=client.get("legal_name", client["display_name"]),
        subject=f"Amortization schedule for loan {loan}",
        # Provenance stays machine-readable without labelling every printed page.
        keywords=(
            f"SYNTHETIC demo fixture; {fixture.scenario_id}; v{fixture.version}; {variant}; "
            f"{fixture.client_code}"
        ),
        creator="Northstar document services",
    )
    first_due = f"{entries[0]['year']}-{entries[0]['month']:02}-01"
    total_interest = sum(e["interest"] for e in entries)
    total_paid = sum(e["payment"] for e in entries)
    letterhead = Table(
        [
            [
                Paragraph(escape(client["display_name"]), brand),
                Paragraph(
                    "<br/>".join(
                        escape(v)
                        for v in (
                            client.get("mailing_address", ""),
                            f"Customer Care {client.get('support_phone', '')}",
                            client.get("website", ""),
                        )
                        if v.strip()
                    ),
                    right,
                ),
            ]
        ],
        colWidths=[300, 216],
    )
    letterhead.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 1.2, ink),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story = [
        letterhead,
        Spacer(1, 14),
        Paragraph(escape(document.title), heading),
        Paragraph(f"Prepared {long_date(fixture.evaluation_at.date().isoformat())}", small),
        Spacer(1, 10),
    ]

    def boxed(rows, widths):
        table = Table(rows, colWidths=widths)
        table.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("TEXTCOLOR", (0, 0), (-1, -1), ink),
                    ("TEXTCOLOR", (0, 0), (0, -1), muted),
                    ("TEXTCOLOR", (2, 0), (2, -1), muted),
                    ("BACKGROUND", (0, 0), (-1, -1), band),
                    ("BOX", (0, 0), (-1, -1), 0.5, rule),
                    ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        return table

    story += [
        boxed(
            [
                ["Borrower", party["borrower"], "Loan number", loan],
                ["Mailing address", party["mailing_address"], "Loan type", "30-year fixed rate"],
                ["Property address", party["property_address"], "Occupancy", "Primary residence"],
            ],
            [80, 196, 82, 158],
        ),
        Paragraph("Loan terms", section),
        boxed(
            [
                [
                    "Original principal",
                    money(facts["original_principal_minor"]),
                    "Interest rate",
                    f"{facts['annual_rate_basis_points'] / 100:.3f}% fixed",
                ],
                [
                    "Note date",
                    long_date(facts["note_date"]),
                    "Loan term",
                    f"{facts['term_months']} months",
                ],
                [
                    "Unpaid principal balance",
                    money(facts["opening_principal_minor"]),
                    "Monthly principal and interest",
                    money(entries[0]["payment"]),
                ],
                [
                    "Next payment due",
                    long_date(first_due),
                    "Remaining payments",
                    f"{len(entries)} (payments {entries[0]['number']}-{entries[-1]['number']})",
                ],
                [
                    "Scheduled maturity",
                    long_date(facts["maturity_date"]),
                    "Escrow",
                    "Not included in this schedule",
                ],
            ],
            [110, 150, 130, 126],
        ),
        Paragraph("About this schedule", section),
        *[
            Paragraph(escape(text), ParagraphStyle("para", parent=body, spaceAfter=5))
            for text in document.paragraphs
        ],
    ]

    years: dict[int, dict] = {}
    for e in entries:
        y = years.setdefault(e["year"], {"count": 0, "principal": 0, "interest": 0})
        y["count"] += 1
        y["principal"] += e["principal"]
        y["interest"] += e["interest"]
        y["balance"] = e["balance"]
    annual = [["Year", "Payments", "Principal", "Interest", "Year-end balance"]]
    annual += [
        [
            str(year),
            str(v["count"]),
            money(v["principal"]),
            money(v["interest"]),
            money(v["balance"]),
        ]
        for year, v in years.items()
    ]
    annual.append(
        [
            "Total",
            str(len(entries)),
            money(sum(e["principal"] for e in entries)),
            money(total_interest),
            "",
        ]
    )

    def grid(rows, widths, total_row=False):
        table = Table(rows, colWidths=widths, repeatRows=1)
        style = [
            ("FONTSIZE", (0, 0), (-1, -1), 7.8),
            ("LEADING", (0, 0), (-1, -1), 9.5),
            ("TEXTCOLOR", (0, 0), (-1, -1), ink),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe7ee")),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, ink),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fa")]),
        ]
        if total_row:
            style += [
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("LINEABOVE", (0, -1), (-1, -1), 0.8, ink),
            ]
        table.setStyle(TableStyle(style))
        return table

    story += [
        Paragraph("Summary of remaining payments", section),
        boxed(
            [
                [
                    "Total of remaining payments",
                    money(total_paid),
                    "Total interest",
                    money(total_interest),
                ],
                [
                    "Final payment amount",
                    money(entries[-1]["payment"]),
                    "Final payment due",
                    long_date(facts["maturity_date"]),
                ],
            ],
            [130, 128, 110, 148],
        ),
        Spacer(1, 6),
        KeepTogether(
            [Paragraph("Annual summary", section), grid(annual, [70, 70, 125, 115, 136], True)]
        ),
        CondPageBreak(160),
        Paragraph("Payment schedule", section),
    ]
    schedule = [["Pmt no.", "Due date", "Payment", "Principal", "Interest", "Balance"]]
    schedule += [
        [
            str(e["number"]),
            f"{e['month']:02}/01/{e['year']}",
            money(e["payment"]),
            money(e["principal"]),
            money(e["interest"]),
            money(e["balance"]),
        ]
        for e in entries
    ]
    table = grid(schedule, [52, 78, 92, 92, 92, 110])
    table.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "CENTER")]))
    story += [
        table,
        Spacer(1, 14),
        Paragraph("Questions", section),
        Paragraph(
            escape(
                f"Reply to this email or call Customer Care at {client.get('support_phone', '')}, "
                f"{client.get('support_hours', '')}. Written correspondence may be sent to "
                f"{client.get('legal_name', client['display_name'])}, {client.get('mailing_address', '')}. "
                "Please include your loan number on all correspondence."
            ),
            body,
        ),
    ]
    footer = f"{client['display_name']}  |  Loan {loan}  |  {party['borrower']}"
    pdf.build(story, canvasmaker=_NumberedCanvas(footer))
    return buffer.getvalue()


def _provenance(fixture, document, variant: str) -> str:
    """Machine-readable identity kept out of the printed page (checked by check-data)."""
    loan = document.declared_loan_identifier or fixture.loan_identifier
    return (
        f"SYNTHETIC demo fixture; {fixture.scenario_id}; v{fixture.version}; {variant}; "
        f"{fixture.client_code}; loan {loan}; {document.title}"
    )


class _Signature:
    """Pen-style signature (italic name plus a flourish) for signed documents."""

    def __new__(cls, name: str, size: float = 22, width: float = 240):
        from reportlab.platypus import Flowable

        class Signature(Flowable):
            def wrap(self, *_):
                return width, size + 10

            def draw(self):
                canvas = self.canv
                ink = colors.HexColor("#1f3a8a")
                canvas.saveState()
                canvas.setFillColor(ink)
                canvas.setStrokeColor(ink)
                canvas.setFont("Times-BoldItalic", size)
                canvas.translate(6, 9)
                canvas.rotate(2)
                canvas.drawString(0, 0, name)
                text_width = canvas.stringWidth(name, "Times-BoldItalic", size)
                canvas.setLineWidth(0.9)
                path = canvas.beginPath()
                path.moveTo(-4, -4)
                path.curveTo(text_width * 0.3, -9, text_width * 0.7, 1, text_width + 10, -5)
                canvas.drawPath(path, stroke=1, fill=0)
                canvas.restoreState()

        return Signature()


def render_name_change_request(fixture, document, variant: str) -> bytes:
    """The borrower's own signed and dated letter, as scanned and attached to the email."""
    from reportlab.lib.styles import ParagraphStyle

    facts, context = document.facts, fixture.loan_context
    loan = document.declared_loan_identifier or fixture.loan_identifier
    client = client_settings(fixture.client_code)
    previous = facts.get("previous_name") or context.get("current_legal_name", "")
    requested = facts.get("requested_name") or context.get("requested_legal_name", "")
    address = context.get("mailing_address", "")
    street, _, locality = address.partition(", ")
    ink = colors.HexColor("#1b1b1b")
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "letter",
        parent=base["Normal"],
        fontName="Times-Roman",
        fontSize=11.5,
        leading=16,
        textColor=ink,
        spaceAfter=10,
    )
    tight = ParagraphStyle("tight", parent=body, spaceAfter=0)
    bold = ParagraphStyle("bold", parent=tight, fontName="Times-Bold")

    buffer = BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=(612, 792),
        rightMargin=72,
        leftMargin=72,
        topMargin=64,
        bottomMargin=64,
        invariant=1,
        title=f"Name change request - Loan {loan}",
        author=requested,
        subject=f"{document.title} for loan {loan}",
        keywords=_provenance(fixture, document, variant),
        creator="Scanned document",
    )

    def lines(*values, style=tight):
        return Paragraph("<br/>".join(escape(v) for v in values if v), style)

    signed = long_date(facts["signed_date"]) if facts.get("signed_date") else ""
    reason = facts.get("reason", "").replace("_", " ").capitalize()
    details = Table(
        [
            ["Current name on the loan:", previous],
            ["New legal name:", requested],
            *([["Reason for the change:", reason]] if reason else []),
        ],
        colWidths=[150, 318],
        hAlign="LEFT",
    )
    details.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Times-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Times-Roman"),
                ("FONTSIZE", (0, 0), (-1, -1), 11.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
            ]
        )
    )
    story = [
        lines(requested, f"(formerly {previous})", street, locality),
        lines(context.get("borrower_phone", ""), fixture.borrower_email),
        Spacer(1, 22),
        lines(signed),
        Spacer(1, 18),
        lines(
            client.get("legal_name", client["display_name"]),
            "Attn: Customer Correspondence",
            *client.get("mailing_address", "").split(", ", 1),
        ),
        Spacer(1, 18),
        lines("Re: Request to change the borrower name on my loan", style=bold),
        lines(f"Loan number: {loan}", f"Property: {context.get('property_address', '')}"),
        Spacer(1, 16),
        Paragraph("To whom it may concern:", body),
        *[Paragraph(escape(text), body) for text in document.paragraphs],
        details,
        Spacer(1, 22),
        Paragraph("Sincerely,", tight),
        _Signature(requested),
        lines(requested, f"Signed and dated: {signed}"),
    ]
    pdf.build(story)
    return buffer.getvalue()


def render_marriage_record(fixture, document, variant: str) -> bytes:
    """Certified copy of a (fictional) county probate-court marriage record."""
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import ParagraphStyle

    facts = document.facts
    ink, muted, rule = (
        colors.HexColor("#1d2b36"),
        colors.HexColor("#55636e"),
        colors.HexColor("#7b8a96"),
    )
    base = getSampleStyleSheet()
    center = ParagraphStyle(
        "center",
        parent=base["Normal"],
        fontName="Times-Roman",
        fontSize=10.5,
        leading=14,
        alignment=TA_CENTER,
        textColor=ink,
    )
    state = ParagraphStyle("state", parent=center, fontName="Times-Bold", fontSize=12, leading=15)
    court = ParagraphStyle("court", parent=center, fontName="Times-Bold", fontSize=16, leading=20)
    title = ParagraphStyle(
        "title", parent=center, fontName="Times-Bold", fontSize=14, leading=18, spaceBefore=10
    )
    body = ParagraphStyle(
        "body", parent=center, alignment=0, fontSize=10.5, leading=14.5, spaceAfter=6
    )
    residence = ", ".join(
        part.strip() for part in fixture.loan_context.get("mailing_address", "").split(",")[1:2]
    )
    residence = f"{residence}, Ohio" if residence else ""
    authority = facts.get("issuing_authority", "")

    buffer = BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=(612, 792),
        rightMargin=66,
        leftMargin=66,
        topMargin=70,
        bottomMargin=70,
        invariant=1,
        title=f"{document.title} - {facts.get('license_number', '')}",
        author=authority,
        subject=f"{document.title}; supplied for loan {fixture.loan_identifier}",
        keywords=_provenance(fixture, document, variant),
        creator="Scanned document",
    )
    parties = Table(
        [
            ["", "PARTY 1", "PARTY 2"],
            [
                "Full name before marriage",
                facts.get("previous_full_name", facts.get("previous_name", "")),
                facts.get("spouse_name", ""),
            ],
            [
                "Name after marriage",
                facts.get("new_full_name", facts.get("new_name", "")),
                facts.get("spouse_name", ""),
            ],
            ["Residence", residence, residence],
        ],
        colWidths=[150, 165, 165],
    )
    parties.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Times-Roman"),
                ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
                ("FONTNAME", (0, 1), (0, -1), "Times-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10.5),
                ("TEXTCOLOR", (0, 0), (-1, -1), ink),
                ("GRID", (0, 0), (-1, -1), 0.5, rule),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f3")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    record = Table(
        [
            ["Date of marriage", long_date(facts["marriage_date"])],
            ["Place of marriage", facts.get("marriage_place", "")],
            ["Solemnized by", facts.get("officiant", "")],
            ["Marriage license number", facts.get("license_number", "")],
            ["Date recorded", long_date(facts["recorded_date"])],
        ],
        colWidths=[150, 330],
    )
    record.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Times-Roman"),
                ("FONTNAME", (0, 0), (0, -1), "Times-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10.5),
                ("TEXTCOLOR", (0, 0), (-1, -1), ink),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, rule),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    officer, _, role = facts.get("certifying_officer", "").partition(", ")
    story = [
        Paragraph("STATE OF OHIO", state),
        Paragraph(escape(authority.replace(", Ohio", "").upper()), court),
        Paragraph("Marriage License Department", center),
        Paragraph(escape(document.title), title),
        Paragraph(escape(f"License No. {facts.get('license_number', '')}"), center),
        Spacer(1, 18),
        parties,
        Spacer(1, 14),
        record,
        Spacer(1, 18),
        *[Paragraph(escape(text), body) for text in document.paragraphs],
        Paragraph(
            escape(
                "Witness my hand and the seal of this court on "
                f"{long_date(facts['certified_date'])}."
            ),
            body,
        ),
        Spacer(1, 10),
        _Signature(officer, size=19),
        Paragraph(escape(officer), ParagraphStyle("o", parent=body, spaceAfter=0)),
        Paragraph(escape(f"{role}, {authority}"), ParagraphStyle("r", parent=body)),
    ]

    def frame(canvas, _):
        canvas.saveState()
        canvas.setStrokeColor(ink)
        canvas.setLineWidth(2)
        canvas.rect(36, 36, 540, 720)
        canvas.setLineWidth(0.6)
        canvas.rect(42, 42, 528, 708)
        canvas.setFont("Times-Italic", 7.5)
        canvas.setFillColor(muted)
        canvas.drawCentredString(
            306,
            50,
            "Demonstration record prepared for software testing. "
            "Not an official document and not valid for identification.",
        )
        canvas.restoreState()

    pdf.build(story, onFirstPage=frame, onLaterPages=frame)
    return buffer.getvalue()


def render_tax_bill(fixture, document, variant: str) -> bytes:
    """Municipal real-estate tax bill (fictional township) with a remittance stub."""
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle

    facts = document.facts
    ink, muted, rule, band = (
        colors.HexColor("#1f2a33"),
        colors.HexColor("#56636d"),
        colors.HexColor("#8795a1"),
        colors.HexColor("#eef1f4"),
    )
    base = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=base["Normal"], fontSize=8.6, leading=11.6, textColor=ink)
    small = ParagraphStyle("small", parent=body, fontSize=7.8, leading=10, textColor=muted)
    right = ParagraphStyle("right", parent=small, alignment=TA_RIGHT)
    office = ParagraphStyle(
        "office", parent=body, fontName="Helvetica-Bold", fontSize=14, leading=17
    )
    title = ParagraphStyle(
        "title",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=12.5,
        leading=16,
        alignment=TA_CENTER,
        spaceBefore=4,
    )
    subtitle = ParagraphStyle("subtitle", parent=small, alignment=TA_CENTER)
    section = ParagraphStyle(
        "section", parent=body, fontName="Helvetica-Bold", spaceBefore=8, spaceAfter=3
    )
    note = ParagraphStyle("note", parent=body, fontSize=8, leading=10.8, spaceAfter=3.5)
    payee = facts.get("payee", "")
    township = payee.replace(" Tax Collector", "")
    installment = facts.get("amount_minor", 0)
    due = long_date(facts["due_date"])
    period = (
        f"{long_date(facts['billing_period_start'])} through "
        f"{long_date(facts['billing_period_end'])}"
        if facts.get("billing_period_start") and facts.get("billing_period_end")
        else ""
    )
    number = facts.get("installment_number")
    count = facts.get("installment_count")
    ordinal = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}.get(number, str(number))
    penalty = (Decimal(installment) * Decimal("1.10")).quantize(Decimal(1), ROUND_HALF_UP)
    street, _, locality = facts.get("property_address", "").partition(", ")
    year = (facts.get("billing_period_start") or facts.get("issued_date") or "")[:4]

    buffer = BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=(612, 792),
        rightMargin=46,
        leftMargin=46,
        topMargin=40,
        bottomMargin=50,
        invariant=1,
        title=f"{document.title} - Bill {facts.get('bill_number', '')}",
        author=payee,
        subject=f"{document.title}; supplied for loan {fixture.loan_identifier}",
        keywords=_provenance(fixture, document, variant),
        creator="Scanned document",
    )

    def kv(rows, widths, shaded=True):
        table = Table(rows, colWidths=widths)
        style = [
            ("FONTSIZE", (0, 0), (-1, -1), 8.4),
            ("TEXTCOLOR", (0, 0), (-1, -1), ink),
            ("TEXTCOLOR", (0, 0), (0, -1), muted),
            ("BOX", (0, 0), (-1, -1), 0.6, rule),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]
        if shaded:
            style.append(("BACKGROUND", (0, 0), (-1, -1), band))
        if len(widths) == 4:
            style.append(("TEXTCOLOR", (2, 0), (2, -1), muted))
        table.setStyle(TableStyle(style))
        return table

    header = Table(
        [
            [
                [
                    Paragraph(escape(township.upper()), office),
                    Paragraph("Office of the Tax Collector", body),
                    Paragraph(
                        "<br/>".join(
                            escape(v)
                            for v in (
                                *facts.get("collector_address", "").split(", ", 1),
                                f"Phone {facts.get('collector_phone', '')}",
                                facts.get("collector_hours", ""),
                            )
                            if v.strip()
                        ),
                        small,
                    ),
                ],
                Paragraph(
                    "<br/>".join(
                        [
                            f"<b>Bill number</b> {escape(facts.get('bill_number', ''))}",
                            f"<b>Date issued</b> {long_date(facts['issued_date'])}"
                            if facts.get("issued_date")
                            else "",
                            f"<b>Parcel ID</b> {escape(facts.get('parcel_id', ''))}",
                            f"<b>Block</b> {escape(facts.get('block', ''))} "
                            f"<b>Lot</b> {escape(facts.get('lot', ''))}",
                        ]
                    ),
                    right,
                ),
            ]
        ],
        colWidths=[330, 190],
    )
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 1.4, ink),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story = [
        header,
        Spacer(1, 8),
        Paragraph(escape(f"{year} REAL ESTATE TAX BILL"), title),
        Paragraph(
            escape(
                f"{ordinal} Quarter Installment ({number} of {count})"
                + (f"  |  Billing period {period}" if period else "")
            ),
            subtitle,
        ),
        Spacer(1, 8),
        kv(
            [
                [
                    "Owner of record",
                    facts.get("owner_name", ""),
                    "Assessed value",
                    money(facts.get("assessed_value_minor", 0)),
                ],
                [
                    "Property location",
                    street,
                    "Annual tax",
                    money(facts.get("annual_tax_minor", 0)),
                ],
                ["", locality, "This installment", money(installment)],
            ],
            [92, 206, 100, 122],
        ),
        Spacer(1, 6),
    ]
    if facts.get("mortgage_company"):
        stamp = Table(
            [
                [
                    Paragraph(
                        "<b>MORTGAGE COMPANY COPY SENT</b> - a copy of this bill was sent to "
                        f"<b>{escape(facts['mortgage_company'])}</b>, which is on file to pay "
                        "taxes on this parcel from the owner's escrow account. This copy is for "
                        "your records.",
                        body,
                    )
                ]
            ],
            colWidths=[520],
        )
        stamp.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 1.1, ink),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff7e0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story += [stamp]
    levies = [["Taxing authority", "Millage", "Annual tax", "This installment"]]
    levies += [
        [row["name"], row["mills"], money(row["annual_minor"]), money(row["installment_minor"])]
        for row in facts.get("levies", [])
    ]
    levies.append(
        [
            "Total",
            f"{sum(Decimal(r['mills']) for r in facts.get('levies', [])):.2f}",
            money(facts.get("annual_tax_minor", 0)),
            money(installment),
        ]
    )
    grid = Table(levies, colWidths=[220, 80, 110, 110])
    grid.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 8.4),
                ("TEXTCOLOR", (0, 0), (-1, -1), ink),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dde3e8")),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, ink),
                ("LINEABOVE", (0, -1), (-1, -1), 0.8, ink),
                ("BOX", (0, 0), (-1, -1), 0.6, rule),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    amount = Table(
        [
            [f"Amount due on or before {due}", money(installment)],
            ["Amount due after the due date (includes 10% penalty)", money(penalty)],
        ],
        colWidths=[380, 140],
    )
    amount.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10.5),
                ("FONTSIZE", (0, 1), (-1, 1), 8.4),
                ("TEXTCOLOR", (0, 0), (-1, -1), ink),
                ("TEXTCOLOR", (0, 1), (-1, 1), muted),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("BOX", (0, 0), (-1, -1), 1.1, ink),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story += [
        Paragraph("Tax detail", section),
        grid,
        Spacer(1, 8),
        amount,
        Paragraph("Important information", section),
        *[Paragraph(escape(text), note) for text in document.paragraphs],
        Spacer(1, 10),
        Paragraph(
            "- - - - - - - - - - - - - - - - - - - - - -  Detach and return this portion with "
            "your payment  - - - - - - - - - - - - - - - - - - - - - -",
            ParagraphStyle("cut", parent=small, alignment=TA_CENTER),
        ),
        Spacer(1, 6),
        Paragraph(
            escape(f"REMITTANCE STUB  |  {year} Real Estate Tax  |  {ordinal} Quarter Installment"),
            ParagraphStyle("stub", parent=body, fontName="Helvetica-Bold"),
        ),
        Spacer(1, 4),
        kv(
            [
                ["Bill number", facts.get("bill_number", ""), "Due date", due],
                ["Parcel ID", facts.get("parcel_id", ""), "Amount due", money(installment)],
                ["Owner", facts.get("owner_name", ""), "Amount enclosed", "$ ______________"],
                ["Pay to", payee, "", ""],
                ["", facts.get("collector_address", "").split(", ", 1)[-1], "", ""],
            ],
            [80, 240, 90, 110],
            shaded=False,
        ),
    ]

    def footer(canvas, _):
        canvas.saveState()
        canvas.setFont("Helvetica-Oblique", 7)
        canvas.setFillColor(muted)
        canvas.drawCentredString(
            306,
            28,
            "Demonstration record prepared for software testing. "
            "Not an official tax bill; no real parcel or tax obligation exists.",
        )
        canvas.restoreState()

    pdf.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def render_escrow_analysis(fixture, document, variant: str) -> bytes:
    """Servicer's annual escrow account disclosure statement with a surplus refund."""
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import KeepTogether

    facts, context = document.facts, fixture.loan_context
    loan = document.declared_loan_identifier or fixture.loan_identifier
    client = client_settings(fixture.client_code)
    ink, muted, rule, band = (
        colors.HexColor("#14213d"),
        colors.HexColor("#5b6770"),
        colors.HexColor("#c9d3dc"),
        colors.HexColor("#eef2f6"),
    )
    base = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=base["Normal"], fontSize=9, leading=13, textColor=ink)
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=11, textColor=muted)
    brand = ParagraphStyle("brand", parent=body, fontName="Helvetica-Bold", fontSize=15, leading=18)
    heading = ParagraphStyle(
        "heading", parent=body, fontName="Helvetica-Bold", fontSize=13, leading=17, spaceAfter=2
    )
    section = ParagraphStyle(
        "section",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=14,
        spaceBefore=10,
        spaceAfter=4,
    )
    right = ParagraphStyle("right", parent=small, alignment=TA_RIGHT)
    para = ParagraphStyle("para", parent=body, spaceAfter=5)

    buffer = BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=(612, 792),
        rightMargin=48,
        leftMargin=48,
        topMargin=44,
        bottomMargin=52,
        invariant=1,
        title=f"{document.title} - Loan {loan}",
        author=client.get("legal_name", client["display_name"]),
        subject=f"Escrow account analysis for loan {loan}",
        keywords=_provenance(fixture, document, variant),
        creator="Scanned document",
    )
    letterhead = Table(
        [
            [
                Paragraph(escape(client["display_name"]), brand),
                Paragraph(
                    "<br/>".join(
                        escape(v)
                        for v in (
                            client.get("mailing_address", ""),
                            f"Customer Care {client.get('support_phone', '')}",
                            client.get("website", ""),
                        )
                        if v.strip()
                    ),
                    right,
                ),
            ]
        ],
        colWidths=[300, 216],
    )
    letterhead.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 1.2, ink),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    def boxed(rows, widths):
        table = Table(rows, colWidths=widths)
        table.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("TEXTCOLOR", (0, 0), (-1, -1), ink),
                    ("TEXTCOLOR", (0, 0), (0, -1), muted),
                    ("TEXTCOLOR", (2, 0), (2, -1), muted),
                    ("BACKGROUND", (0, 0), (-1, -1), band),
                    ("BOX", (0, 0), (-1, -1), 0.5, rule),
                    ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        return table

    def grid(rows, widths, bold_last=True):
        table = Table(rows, colWidths=widths)
        style = [
            ("FONTSIZE", (0, 0), (-1, -1), 8.4),
            ("TEXTCOLOR", (0, 0), (-1, -1), ink),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe7ee")),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, ink),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("BOX", (0, 0), (-1, -1), 0.5, rule),
        ]
        if bold_last:
            style += [
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("LINEABOVE", (0, -1), (-1, -1), 0.8, ink),
            ]
        table.setStyle(TableStyle(style))
        return table

    effective = long_date(facts["new_payment_effective_date"])
    payments = grid(
        [
            ["", "Current payment", f"New payment beginning {effective}"],
            [
                "Principal and interest",
                money(facts["principal_interest_minor"]),
                money(facts["principal_interest_minor"]),
            ],
            [
                "Escrow deposit",
                money(facts["current_escrow_minor"]),
                money(facts["new_escrow_minor"]),
            ],
            [
                "Total monthly payment",
                money(facts["current_payment_minor"]),
                money(facts["new_payment_minor"]),
            ],
        ],
        [196, 140, 180],
    )
    disbursements = [["Month", "Paid to", "Description", "Amount"]]
    for row in facts.get("projected_disbursements", []):
        year, month = map(int, row["month"].split("-"))
        disbursements.append(
            [
                f"{MONTHS[month - 1]} {year}",
                row["payee"],
                row["description"],
                money(row["amount_minor"]),
            ]
        )
    disbursements.append(["Total for the year", "", "", money(facts["annual_disbursements_minor"])])
    projected = grid(disbursements, [96, 170, 160, 90])
    projected.setStyle(TableStyle([("ALIGN", (1, 0), (2, -1), "LEFT")]))
    analysis = long_date(facts["analysis_date"])
    surplus = Table(
        [
            ["Projected lowest escrow balance", money(facts["projected_low_balance_minor"])],
            [
                "Required cushion (two months of escrow deposits)",
                money(facts["required_cushion_minor"]),
            ],
            ["Escrow surplus", money(facts["surplus_minor"])],
        ],
        colWidths=[380, 136],
    )
    surplus.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 8.8),
                ("TEXTCOLOR", (0, 0), (-1, -1), ink),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, -1), (-1, -1), 10.5),
                ("LINEABOVE", (0, -1), (-1, -1), 0.8, ink),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("BOX", (0, 0), (-1, -1), 1.1, ink),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story = [
        letterhead,
        Spacer(1, 14),
        Paragraph(escape(document.title), heading),
        Paragraph(
            escape(
                f"Statement date {analysis}  |  Computation year "
                f"{long_date(facts['computation_start'])} through "
                f"{long_date(facts['computation_end'])}"
            ),
            small,
        ),
        Spacer(1, 10),
        boxed(
            [
                ["Borrower", fixture.borrower_display_name, "Loan number", loan],
                [
                    "Mailing address",
                    context.get("mailing_address", ""),
                    "Loan type",
                    f"{context.get('term_months', 0) // 12}-year fixed rate",
                ],
                [
                    "Property address",
                    context.get("property_address", ""),
                    "Statement date",
                    analysis,
                ],
            ],
            [80, 196, 82, 158],
        ),
        Paragraph("Your monthly payment", section),
        payments,
        Paragraph("Projected escrow disbursements for the coming year", section),
        projected,
        Paragraph(
            escape(
                f"New monthly escrow deposit: {money(facts['annual_disbursements_minor'])} "
                f"divided by 12 = {money(facts['new_escrow_minor'])}."
            ),
            ParagraphStyle("calc", parent=small, spaceBefore=3),
        ),
        Paragraph("Escrow surplus", section),
        surplus,
        Spacer(1, 6),
        Paragraph(
            escape(
                f"Refund: a check for {money(facts['surplus_minor'])} will be mailed to you "
                f"within {facts.get('refund_within_days', 30)} days of {analysis}."
            ),
            ParagraphStyle("refund", parent=body, fontName="Helvetica-Bold"),
        ),
        Paragraph("About this statement", section),
        *[Paragraph(escape(text), para) for text in document.paragraphs],
        KeepTogether(
            [
                Paragraph("Questions", section),
                Paragraph(
                    escape(
                        "Reply to this email or call Customer Care at "
                        f"{client.get('support_phone', '')}, {client.get('support_hours', '')}. "
                        "Written correspondence may be sent to "
                        f"{client.get('legal_name', client['display_name'])}, "
                        f"{client.get('mailing_address', '')}. Please include your loan number "
                        "on all correspondence."
                    ),
                    body,
                ),
            ]
        ),
    ]
    footer = f"{client['display_name']}  |  Loan {loan}  |  {fixture.borrower_display_name}"
    pdf.build(story, canvasmaker=_NumberedCanvas(footer))
    return buffer.getvalue()


def render_email_printout(fixture, document, variant: str) -> bytes:
    """A borrower's email as printed from the correspondence inbox."""
    from reportlab.lib.styles import ParagraphStyle

    facts = document.facts
    client = client_settings(fixture.client_code)
    ink, muted, rule = (
        colors.HexColor("#1f2328"),
        colors.HexColor("#59636e"),
        colors.HexColor("#d0d7de"),
    )
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "body", parent=base["Normal"], fontSize=10.5, leading=15, textColor=ink, spaceAfter=9
    )
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=10, textColor=muted)
    subject = ParagraphStyle(
        "subject", parent=body, fontName="Helvetica-Bold", fontSize=13, leading=17
    )
    buffer = BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=(612, 792),
        rightMargin=60,
        leftMargin=60,
        topMargin=48,
        bottomMargin=56,
        invariant=1,
        title=facts.get("reply_subject", document.title),
        author=fixture.borrower_display_name,
        subject=f"{document.title}; loan {fixture.loan_identifier}",
        keywords=_provenance(fixture, document, variant),
        creator="Correspondence inbox print",
    )
    sender = facts.get("reply_from") or fixture.borrower_email
    header = Table(
        [
            ["From", f"{fixture.borrower_display_name} <{sender}>"],
            ["To", f"{client['display_name']} <correspondence@servicing.example.com>"],
            ["Received", long_date(fixture.evaluation_at.date().isoformat())],
        ],
        colWidths=[62, 430],
        hAlign="LEFT",
    )
    header.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), muted),
                ("TEXTCOLOR", (1, 0), (1, -1), ink),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ("LINEBELOW", (0, -1), (-1, -1), 0.8, rule),
            ]
        )
    )
    story = [
        Paragraph(escape(f"{client['display_name']} - correspondence inbox"), small),
        Spacer(1, 8),
        Paragraph(escape(facts.get("reply_subject", document.title)), subject),
        Spacer(1, 6),
        header,
        Spacer(1, 16),
        *[
            Paragraph("<br/>".join(escape(line) for line in text.split("\n")), body)
            for text in document.paragraphs
        ],
    ]
    pdf.build(story)
    return buffer.getvalue()


def _plain_table(rows, widths, font="Times-Roman", size=10.5, bold_first=True, ink=None):
    table = Table(rows, colWidths=widths, hAlign="LEFT")
    style = [
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), size),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    if bold_first:
        style.append(("FONTNAME", (0, 0), (0, -1), font.split("-")[0] + "-Bold"))
    if ink is not None:
        style.append(("TEXTCOLOR", (0, 0), (-1, -1), ink))
    table.setStyle(TableStyle(style))
    return table


def render_court_order(fixture, document, variant: str) -> bytes:
    """Order dismissing a Chapter 13 case (fictional court and district) with a docket excerpt."""
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import ParagraphStyle

    facts = document.facts
    ink, muted, rule = (
        colors.HexColor("#1b1b1b"),
        colors.HexColor("#5a5a5a"),
        colors.HexColor("#444444"),
    )
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "order",
        parent=base["Normal"],
        fontName="Times-Roman",
        fontSize=11,
        leading=15,
        textColor=ink,
        spaceAfter=6,
    )
    center = ParagraphStyle("center", parent=body, alignment=TA_CENTER, spaceAfter=0)
    court = ParagraphStyle("court", parent=center, fontName="Times-Bold", fontSize=13, leading=17)
    title = ParagraphStyle(
        "title", parent=center, fontName="Times-Bold", fontSize=12.5, spaceBefore=14
    )
    small = ParagraphStyle("small", parent=body, fontSize=9, leading=12, spaceAfter=0)
    case_number = facts.get("case_number", "")
    judge = facts.get("judge", "")
    initials = "".join(part[0] for part in judge.replace(".", "").split() if part[0].isupper())
    chapter = facts.get("chapter", 13)
    district = facts.get("district", "")
    buffer = BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=(612, 792),
        rightMargin=72,
        leftMargin=72,
        topMargin=48,
        bottomMargin=58,
        invariant=1,
        title=f"{document.title}",
        author=f"{facts.get('court', '')}, {district}",
        subject=f"{document.title}; supplied for loan {fixture.loan_identifier}",
        keywords=_provenance(fixture, document, variant),
        creator="Court electronic filing system",
    )
    caption = Table(
        [
            [
                Paragraph(
                    "In re:<br/><br/>"
                    f"{escape(facts.get('debtor_name', '').upper())},<br/><br/>"
                    "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Debtor.<br/><br/>"
                    "Last four digits of Social Security No.: "
                    f"xxx-xx-{escape(str(facts.get('debtor_ssn_last4', '')))}",
                    ParagraphStyle("cap", parent=body, spaceAfter=0),
                ),
                Paragraph(
                    f"Chapter {chapter}<br/><br/>"
                    f"Case No. {escape(case_number)} ({escape(initials)})<br/><br/>"
                    f"Re: Docket No. {facts.get('motion_docket_number', '')}",
                    ParagraphStyle("cap2", parent=body, spaceAfter=0),
                ),
            ]
        ],
        colWidths=[270, 198],
    )
    caption.setStyle(
        TableStyle(
            [
                ("LINEAFTER", (0, 0), (0, 0), 0.8, rule),
                ("LINEBELOW", (0, 0), (0, 0), 0.8, rule),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("LEFTPADDING", (1, 0), (1, 0), 16),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    docket = [["No.", "Date filed", "Docket text"]] + [
        [
            str(row["number"]),
            long_date(row["date"]),
            Paragraph(escape(row["text"]), small),
        ]
        for row in facts.get("docket", [])
    ]
    docket_table = Table(docket, colWidths=[36, 112, 320], repeatRows=1)
    docket_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Times-Roman"),
                ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (-1, -1), ink),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, rule),
                ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#b5b5b5")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    entered = long_date(facts["record_date"])
    story = [
        Paragraph(escape(facts.get("court", "").upper()), court),
        Paragraph(escape(district.upper()), court),
        Spacer(1, 18),
        caption,
        Paragraph(f"ORDER DISMISSING CHAPTER {chapter} CASE", title),
        Spacer(1, 6),
        *[Paragraph(escape(text), body) for text in document.paragraphs],
        Spacer(1, 4),
        Paragraph(escape(f"Dated: {entered}"), body),
        Spacer(1, 2),
        Table(
            [["", _Signature(judge, size=18, width=220)]],
            colWidths=[248, 220],
            style=[("LEFTPADDING", (0, 0), (-1, -1), 0)],
        ),
        Table(
            [
                [
                    "",
                    Paragraph(
                        f"BY THE COURT:<br/>{escape(judge)}<br/>United States Bankruptcy Judge",
                        ParagraphStyle("judge", parent=body, spaceAfter=0),
                    ),
                ]
            ],
            colWidths=[248, 220],
            style=[("LEFTPADDING", (0, 0), (-1, -1), 0)],
        ),
        Spacer(1, 14),
        Paragraph(
            escape(
                f"Docket excerpt, Case No. {case_number} (selected entries). Filed "
                f"{long_date(facts['filed_date'])}; plan confirmed "
                f"{long_date(facts['plan_confirmed_date'])}. Chapter 13 Trustee: "
                f"{facts.get('trustee', '')}. Attorney for Debtor: "
                f"{facts.get('debtor_attorney', '')}."
            ),
            small,
        ),
        Spacer(1, 6),
        docket_table,
    ]

    def footer(canvas, _):
        canvas.saveState()
        canvas.setFont("Times-Roman", 8.5)
        canvas.setFillColor(muted)
        canvas.drawString(
            72,
            40,
            f"Case {case_number}    Doc {facts.get('order_docket_number', '')}    "
            f"Entered {entered}",
        )
        canvas.setFont("Times-Italic", 7.5)
        canvas.drawCentredString(
            306,
            26,
            "Demonstration record prepared for software testing. "
            "Not an official court record; no real case or court exists.",
        )
        canvas.restoreState()

    pdf.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def render_representation_letter(fixture, document, variant: str) -> bytes:
    """The borrower's signed authorization on the representative's letterhead."""
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import ParagraphStyle

    facts, context = document.facts, fixture.loan_context
    client = client_settings(fixture.client_code)
    ink, muted = colors.HexColor("#1b1b1b"), colors.HexColor("#555555")
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "letter",
        parent=base["Normal"],
        fontName="Times-Roman",
        fontSize=10.5,
        leading=14,
        textColor=ink,
        spaceAfter=7,
    )
    tight = ParagraphStyle("tight", parent=body, spaceAfter=0)
    bold = ParagraphStyle("bold", parent=tight, fontName="Times-Bold")
    firm = facts.get("representative_firm", "")
    head = ParagraphStyle(
        "firm", parent=tight, fontName="Times-Bold", fontSize=17, leading=21, alignment=TA_CENTER
    )
    sub = ParagraphStyle("sub", parent=tight, fontSize=9, leading=12, alignment=TA_CENTER)
    borrower = facts.get("borrower_name") or fixture.borrower_display_name
    representative = facts.get("representative_name", "")
    signed = long_date(facts["signed_date"]) if facts.get("signed_date") else ""
    buffer = BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=(612, 792),
        rightMargin=72,
        leftMargin=72,
        topMargin=54,
        bottomMargin=60,
        invariant=1,
        title=f"{document.title} - Loan {fixture.loan_identifier}",
        author=firm or borrower,
        subject=f"{document.title} for loan {fixture.loan_identifier}",
        keywords=_provenance(fixture, document, variant),
        creator="Scanned document",
    )

    def lines(*values, style=tight):
        return Paragraph("<br/>".join(escape(v) for v in values if v), style)

    letterhead = [
        Paragraph(escape(firm.upper()), head),
        Paragraph(escape(facts.get("firm_practice", "Attorneys at Law")), sub),
        Paragraph(
            escape(
                "  |  ".join(
                    v
                    for v in (
                        facts.get("firm_address", ""),
                        facts.get("representative_phone", ""),
                        facts.get("representative_email", ""),
                    )
                    if v
                )
            ),
            sub,
        ),
    ]
    rule = Table([[""]], colWidths=[468], rowHeights=[6])
    rule.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 1.2, ink)]))
    story = [
        *letterhead,
        rule,
        Spacer(1, 14),
        lines(signed),
        Spacer(1, 10),
        lines(
            client.get("legal_name", client["display_name"]),
            "Attn: Customer Correspondence",
            *client.get("mailing_address", "").split(", ", 1),
        ),
        Spacer(1, 14),
        lines(f"Re: {document.title}", style=bold),
        _plain_table(
            [
                ["Borrower:", borrower],
                ["Loan number:", fixture.loan_identifier],
                ["Property:", context.get("property_address", "")],
                ["Representative:", ", ".join(v for v in (representative, firm) if v)],
            ],
            [100, 368],
            size=10.5,
        ),
        Spacer(1, 12),
        Paragraph("To whom it may concern:", body),
        *[Paragraph(escape(text), body) for text in document.paragraphs],
        Spacer(1, 6),
        _plain_table(
            [
                ["Representative:", representative],
                ["Email:", facts.get("representative_email", "")],
                ["Phone:", facts.get("representative_phone", "")],
            ],
            [100, 368],
            size=10.5,
        ),
        Spacer(1, 14),
        Table(
            [
                [
                    Paragraph("Borrower signature:", tight),
                    Paragraph(escape(facts.get("acceptance_label", "Accepted by counsel:")), tight),
                ],
                [
                    _Signature(borrower, size=20, width=220),
                    _Signature(representative, size=18, width=220),
                ],
                [
                    lines(borrower, f"Signed and dated: {signed}"),
                    lines(representative, firm),
                ],
            ],
            colWidths=[234, 234],
            hAlign="LEFT",
            style=[
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ],
        ),
    ]

    def footer(canvas, _):
        canvas.saveState()
        canvas.setFont("Times-Italic", 7.5)
        canvas.setFillColor(muted)
        canvas.drawCentredString(
            306,
            30,
            "Demonstration record prepared for software testing; fictional representative and firm.",
        )
        canvas.restoreState()

    pdf.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def render_bankruptcy_memo(fixture, document, variant: str) -> bytes:
    """Internal Bankruptcy Team determination memo (not an outgoing attachment)."""
    from reportlab.lib.styles import ParagraphStyle

    facts, context = document.facts, fixture.loan_context
    client = client_settings(fixture.client_code)
    ink, muted, band = (
        colors.HexColor("#1f2a33"),
        colors.HexColor("#56636d"),
        colors.HexColor("#eef1f4"),
    )
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "memo", parent=base["Normal"], fontSize=10, leading=14, textColor=ink, spaceAfter=8
    )
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=10, textColor=muted)
    brand = ParagraphStyle("brand", parent=body, fontName="Helvetica-Bold", fontSize=13)
    title = ParagraphStyle("title", parent=body, fontName="Helvetica-Bold", fontSize=15)
    section = ParagraphStyle(
        "section", parent=body, fontName="Helvetica-Bold", spaceBefore=6, spaceAfter=4
    )
    reviewer = facts.get("reviewed_by", "")
    reviewed = facts.get("reviewed_at", "")[:10]
    buffer = BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=(612, 792),
        rightMargin=56,
        leftMargin=56,
        topMargin=48,
        bottomMargin=56,
        invariant=1,
        title=document.title,
        author=reviewer,
        subject=f"{document.title}; loan {fixture.loan_identifier}",
        keywords=_provenance(fixture, document, variant),
        creator="Servicing workflow",
    )
    header = Table(
        [
            ["To", facts.get("referred_to", "")],
            ["From", reviewer],
            ["Date", long_date(reviewed) if reviewed else ""],
            ["Borrower", fixture.borrower_display_name],
            ["Loan number", fixture.loan_identifier],
            ["Case reference", fixture.ccid],
            ["Reference", facts.get("reference", "")],
        ],
        colWidths=[100, 400],
        hAlign="LEFT",
    )
    header.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, 0), (-1, -1), ink),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LINEBELOW", (0, -1), (-1, -1), 0.8, ink),
            ]
        )
    )
    status = facts.get("determination", "").replace("_", " ")
    summary = Table(
        [
            [
                "Bankruptcy case",
                Paragraph(
                    escape(
                        f"No. {facts.get('case_number', '')}, Chapter "
                        f"{context.get('bankruptcy_chapter', 13)}, "
                        f"{context.get('bankruptcy_court', '')}"
                    ),
                    ParagraphStyle("cell", parent=body, fontSize=9.2, leading=11.5, spaceAfter=0),
                ),
            ],
            [
                "Case dismissed",
                long_date(facts["dismissed_date"])
                + f" (Docket No. {facts.get('order_docket_number', '')})",
            ],
            ["Discharge entered", "Yes" if facts.get("discharge_entered") else "No"],
            [
                "Previous servicing marker",
                f"{facts.get('previous_marker', '').capitalize()} "
                f"({facts.get('previous_marker_source', '')})",
            ],
            ["Determined status", status.capitalize()],
            [
                "Communication",
                "Counsel only: "
                + ", ".join(
                    v
                    for v in (
                        context.get("representative_name"),
                        context.get("representative_firm"),
                    )
                    if v
                ),
            ],
            ["Credit reporting", "Not determined here; referred to Compliance"],
        ],
        colWidths=[140, 360],
        hAlign="LEFT",
    )
    summary.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9.2),
                ("TEXTCOLOR", (0, 0), (-1, -1), ink),
                ("TEXTCOLOR", (0, 0), (0, -1), muted),
                ("BACKGROUND", (0, 0), (-1, -1), band),
                ("BOX", (0, 0), (-1, -1), 0.6, muted),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story = [
        Paragraph(escape(client["display_name"]), brand),
        Paragraph("Bankruptcy Team  |  Internal record", small),
        Spacer(1, 12),
        Paragraph(escape(document.title), title),
        Spacer(1, 8),
        header,
        Spacer(1, 12),
        Paragraph("Determination", section),
        summary,
        Spacer(1, 8),
        Paragraph("Findings", section),
        *[Paragraph(escape(text), body) for text in document.paragraphs],
        Spacer(1, 8),
        Paragraph(escape(f"Reviewed by {reviewer}"), small),
    ]

    def footer(canvas, _):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(muted)
        canvas.drawString(
            56, 30, "Internal servicing record. Not for release to the borrower or counsel."
        )
        canvas.drawRightString(556, 30, facts.get("reference", ""))
        canvas.restoreState()

    pdf.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def render_document(fixture, document, variant: str) -> bytes:
    if document.availability == "unreadable":
        return b"%PDF-1.7\nSYNTHETIC intentionally truncated validation fixture\n"
    if document.kind == "amortization_schedule":
        return render_amortization(fixture, document, variant)
    if fixture.scenario_id == "DEMO-01" and document.key == "signed-request":
        return render_name_change_request(fixture, document, variant)
    if fixture.scenario_id == "DEMO-01" and document.facts.get("document_type") == (
        "marriage_record"
    ):
        return render_marriage_record(fixture, document, variant)
    if fixture.scenario_id == "DEMO-03" and document.key == "tax-bill":
        return render_tax_bill(fixture, document, variant)
    if fixture.scenario_id == "DEMO-05" and document.key == "escrow-analysis":
        return render_escrow_analysis(fixture, document, variant)
    if fixture.scenario_id == "DEMO-05" and document.key == "clarification":
        return render_email_printout(fixture, document, variant)
    if fixture.scenario_id == "DEMO-04" and document.key == "court-record":
        return render_court_order(fixture, document, variant)
    if document.key == "representation" and document.facts.get("representative_name"):
        return render_representation_letter(fixture, document, variant)
    if fixture.scenario_id == "DEMO-04" and document.key == "specialist-determination":
        return render_bankruptcy_memo(fixture, document, variant)
    buffer = BytesIO()
    loan = document.declared_loan_identifier or fixture.loan_identifier
    wrong_loan = loan != fixture.loan_identifier
    styles = getSampleStyleSheet()
    styles["Normal"].leading = 16
    styles["Normal"].spaceAfter = 9
    title = document.title
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=(612, 792),
        rightMargin=48,
        leftMargin=48,
        topMargin=48,
        bottomMargin=48,
        invariant=1,
        title=title,
        author="Correspondence synthetic fixture generator",
        subject=f"Synthetic {fixture.scenario_id} {document.key}; loan {loan}",
    )
    story = [
        Paragraph("SYNTHETIC - DEMONSTRATION ONLY", styles["Heading2"]),
        Paragraph(escape(title), styles["Title"]),
        Spacer(1, 0.1 * inch),
    ]
    metadata = [
        ["Loan identifier", loan],
        ["Case reference", "DEMO-CC-099" if wrong_loan else fixture.ccid],
        ["Borrower", "Morgan Example" if wrong_loan else fixture.borrower_display_name],
        ["Client", fixture.client_code],
        ["Document key", document.key],
        ["Fixture version", f"{fixture.scenario_id} / v{fixture.version} / {variant}"],
        ["As of", fixture.evaluation_at.isoformat()],
    ]
    table = Table(metadata, colWidths=[135, 375])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#edf3ef")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([table, Spacer(1, 18)])
    story.extend(Paragraph(escape(text), styles["Normal"]) for text in document.paragraphs)
    if document.kind == "amortization_schedule":
        schedule = Table(
            amortization_rows(document.facts), colWidths=[100, 105, 95, 105, 105], repeatRows=1
        )
        schedule.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dae8df")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.extend([Spacer(1, 10), schedule])
    story.extend(
        [
            Spacer(1, 18),
            Paragraph(
                "Invented records. No real borrower, legal instrument, tax bill, payment or servicing action is represented.",
                styles["Normal"],
            ),
        ]
    )

    def footer(canvas, page):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawString(48, 25, f"SYNTHETIC | Loan {loan} | {document.key}")
        canvas.drawRightString(564, 25, f"Page {page.page}")
        canvas.restoreState()

    pdf.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def build_documents() -> list[dict]:
    manifest = []
    for scenario in SCENARIOS:
        for variant in variants_for(scenario):
            fixture = load_fixture(scenario, variant)
            for document in fixture.documents:
                entry = {
                    "scenario_id": scenario,
                    "variant": variant,
                    "key": document.key,
                    "availability": document.availability,
                    "storage_key": None,
                    "sha256": None,
                }
                if document.availability != "missing":
                    relative = f"{scenario}/{variant}/{document.key}.pdf"
                    content = render_document(fixture, document, variant)
                    path = DATA_ROOT / "documents/v1" / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content)
                    entry.update(storage_key=relative, sha256=hashlib.sha256(content).hexdigest())
                manifest.append(entry)
    write_json(DATA_ROOT / "documents/v1/manifest.json", manifest)
    return manifest


def library_document(scenario: str, variant: str, key: str) -> tuple[dict, bytes | None]:
    manifest = read_json(DATA_ROOT / "documents/v1/manifest.json")
    entry = next(
        row
        for row in manifest
        if (row["scenario_id"], row["variant"], row["key"]) == (scenario, variant, key)
    )
    if not entry["storage_key"]:
        return entry, None
    root = (DATA_ROOT / "documents/v1").resolve()
    path = (root / entry["storage_key"]).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Document manifest path leaves the synthetic library.")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != entry["sha256"]:
        raise DomainError(
            500,
            "document_library_corrupt",
            f"Synthetic document {entry['storage_key']} does not match its recorded hash. "
            "If this checkout came from Git on Windows, line-ending conversion altered the "
            "PDFs: re-checkout data/ with the repository .gitattributes (see README).",
        )
    return entry, content


def library_problems() -> list[str]:
    """Storage keys of synthetic documents whose bytes differ from the manifest."""
    root = (DATA_ROOT / "documents/v1").resolve()
    problems = []
    for row in read_json(DATA_ROOT / "documents/v1/manifest.json"):
        if not row["storage_key"]:
            continue
        path = root / row["storage_key"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            problems.append(row["storage_key"])
    return problems


def document_path(data_dir: Path, evidence: Evidence) -> Path:
    if not evidence.storage_key:
        raise DomainError(404, "document_missing", "This evidence has no available file.")
    root = (data_dir / "documents").resolve()
    path = (root / evidence.storage_key).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise DomainError(404, "document_missing", "The synthetic document is unavailable.")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != evidence.content_sha256:
        raise DomainError(
            409, "document_changed", "The stored document does not match its recorded hash."
        )
    try:
        if evidence.details.get("media_type", "").startswith("image/"):
            from app.mail_attachments import validate_image

            validate_image(content, evidence.details["media_type"])
            return path
        reader = PdfReader(BytesIO(content), strict=True)
        if not reader.pages or (
            evidence.details.get("origin") != "mail_upload"
            and not any(page.extract_text().strip() for page in reader.pages)
        ):
            raise ValueError("No readable text")
    except Exception as exc:
        raise DomainError(
            422, "document_unreadable", "This synthetic validation attachment is unreadable."
        ) from exc
    return path
