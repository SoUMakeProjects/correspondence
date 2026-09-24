"""Deterministic emphasis for outgoing letters.

The checked letter body stays plain text: validation, hashes, the ILS comment and the
``candidate.body`` comparison all depend on it byte for byte. Emphasis is derived *from* that
text by fixed template rules (never chosen by the model), so the same body always produces the
same bold spans, and rendering surfaces (desk UI, HTML mail part, archived PDF) share one source.

Rules:
- In the letter paragraphs (after the salutation, before the signature): dollar amounts, long
  dates, loan references and a fixed list of action/warning phrases from the letter templates.
- In the reference block under the signature: the "Label:" at the start of each line.
Salutation, signature, closing and disclosures are never emphasized.
"""

import re
from html import escape

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"

PATTERNS = [
    re.compile(r"\$\d[\d,]*\.\d{2}"),
    re.compile(rf"\b(?:{MONTHS}) \d{{1,2}}, \d{{4}}\b"),
    re.compile(r"\bloan ending in \d{4}\b"),
    re.compile(r"\bloan \d{6,}\b"),
    re.compile(r"\bOur records now show your name as [^,.\n]+"),
]

# Key actions and warnings, verbatim from the templates in response_validation.py.
PHRASES = (
    "it has not been paid yet",
    "please do not pay this installment yourself",
    "it is not a payoff statement",
    "We have not changed the name on your loan yet",
    "please do not send original documents",
    "no further action is needed from you",
    "we need two documents from you",
    "we need two items from you",
    "Please reply to this email and tell us which one you mean",
    "We have not made any changes to your account",
    "No money will be moved electronically",
    "No money will move until we have received both items and verified the bank account",
    "No payment will be drawn from your bank account",
    "No funds will be advanced",
    "please do not type your bank account number in the body of an email",
    "please continue to make your monthly payments as you do now",
    "please continue to make your payments as scheduled",
    "It is not the result of our investigation",
    "will not contact your client directly",
)

REFERENCE_LINE = re.compile(r"^[A-Z][^:\n]{0,60}:(?= )", re.M)


def _paragraphs(body: str):
    """Yield (start, text) for each blank-line separated paragraph."""
    position = 0
    for part in body.split("\n\n"):
        yield position, part
        position += len(part) + 2


def emphasis_spans(body: str) -> list[list[int]]:
    """Sorted, non-overlapping ``[start, end)`` character spans to render in bold."""
    if not body or not body.startswith("Dear "):
        return []  # Only the deterministic letters are emphasized, not generic renderings.
    spans = []
    signed = False
    for start, text in _paragraphs(body):
        if text.startswith("Dear "):
            continue
        if text.startswith("Sincerely,"):
            signed = True
            continue
        if not signed:
            for pattern in PATTERNS:
                spans += [(start + m.start(), start + m.end()) for m in pattern.finditer(text)]
            for phrase in PHRASES:
                for m in re.finditer(re.escape(phrase), text):
                    spans.append((start + m.start(), start + m.end()))
        else:
            # Only the reference block directly under the signature; disclosures follow it.
            if all(REFERENCE_LINE.match(line) for line in text.split("\n")):
                spans += [
                    (start + m.start(), start + m.end()) for m in REFERENCE_LINE.finditer(text)
                ]
            break
    merged: list[list[int]] = []
    for a, b in sorted(spans):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return merged


def segments(body: str) -> list[tuple[str, bool]]:
    """The body split into ``(text, bold)`` runs."""
    out, cursor = [], 0
    for a, b in emphasis_spans(body):
        if a > cursor:
            out.append((body[cursor:a], False))
        out.append((body[a:b], True))
        cursor = b
    if cursor < len(body):
        out.append((body[cursor:], False))
    return out


def reportlab_markup(body: str) -> str:
    """Escaped ReportLab ``Paragraph`` markup with ``<b>`` emphasis and ``<br/>`` line breaks."""
    return "".join(
        (f"<b>{escape(t, quote=False)}</b>" if bold else escape(t, quote=False)).replace(
            "\n", "<br/>"
        )
        for t, bold in segments(body)
    )


def html_body(body: str) -> str:
    """HTML alternative for the mail: one ``<p>`` per paragraph, ``<strong>`` emphasis."""
    runs = "".join(
        f"<strong>{escape(t)}</strong>" if bold else escape(t) for t, bold in segments(body)
    )
    paragraphs = [p.replace("\n", "<br>") for p in runs.split("\n\n") if p.strip()]
    return "".join(f"<p>{p}</p>" for p in paragraphs)
