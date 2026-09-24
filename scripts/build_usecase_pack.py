"""Build the captured parts of a use-case pack from live evaluation runs.

Usage (from the repository root):

    .venv/bin/python scripts/build_usecase_pack.py --scenario DEMO-03 \
        --out usecases/demo-3-tax-inquiry \
        --mailbox .local/mailbox-evaluations/<id> [--api .local/workflow-evaluations/<id>]

It writes the evidence of what actually happened in the run. The narrative files (README,
people/, organization/) are written by hand.

- correspondence/NN-inbound-*.eml and NN-outbound-*.eml: every mailbox message and every
  delivery, in order, with their attachments
- correspondence/NN-servicing-notes.txt: the ILS final notes
- correspondence/README.md: the thread in readable form
- documents/: the case's source PDFs and the indexed OnBase packages
- rehearsal/live-run-results.json: calls, time, tokens, tools and checks per run and path

Timestamps: the first inbound message uses the case's original receipt time. Everything later
uses the fixture evaluation clock plus the real elapsed time since the first agent run
started, so the thread reads on the demo's business dates, not on the rehearsal date.
"""

import argparse
import json
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
EASTERN = ZoneInfo("America/New_York")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower().replace("–", "-")).strip("-")


def moment(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def rows(db: sqlite3.Connection, sql: str) -> list[dict]:
    db.row_factory = sqlite3.Row
    return [dict(r) for r in db.execute(sql)]


def run_record(path: Path, label: str, db: sqlite3.Connection) -> dict:
    result = json.loads((path / "results.json").read_text())
    case = result["cases"][0]
    first = case["runs"][0]
    runs = []
    for run in case["runs"]:
        checkpoint = run["checkpoint"]
        runs.append(
            {
                "summary": {
                    "run_id": run["id"],
                    "status": run["status"],
                    "reason": checkpoint.get("reason"),
                    "elapsed_seconds": checkpoint.get("elapsed_seconds"),
                    "model_calls": checkpoint.get("model_calls"),
                    "reported_tokens": checkpoint.get("usage", {}).get("total_tokens"),
                    "source": run["model_configuration"].get("source"),
                },
                "usage": checkpoint.get("usage"),
                "tools": [h["tool"] for h in checkpoint.get("history", [])],
                "steps": [
                    {
                        k: h.get(k)
                        for k in ("step", "tool", "status", "code", "message")
                        if k != "message" or h.get("status") == "rejected"
                    }
                    for h in checkpoint.get("history", [])
                ],
            }
        )
    count = {
        name: db.execute(f"select count(*) from {table}").fetchone()[0]
        for name, table in (
            ("deliveries", "outbox_entries"),
            ("packages", "indexed_packages"),
            ("notes", "final_notes"),
        )
    }
    return {
        "path": label,
        "checked_at": result["checked_at"],
        "overall": result["status"],
        "checks": case.get("checks", {}),
        "final_case_status": case.get("case_status")
        or rows(db, "select status from cases")[0]["status"],
        "interventions": case.get("interventions", []),
        "model": {
            k: first["model_configuration"].get(k)
            for k in ("provider", "source", "prompt_version", "tool_contract", "limits")
        },
        "runs": runs,
        **count,
    }


def build(args) -> None:
    from app.fixture_data import load_fixture
    from app.mail_templates import SERVICE_ADDRESS

    fixture = load_fixture(args.scenario)
    out = ROOT / args.out
    source = ROOT / (args.mailbox or args.api)
    db = sqlite3.connect(source / "correspondence.sqlite3")
    docs = source / "documents"
    for folder in ("correspondence", "documents", "rehearsal"):
        target = out / folder
        if target.exists():
            for item in target.glob("*"):
                if item.is_file() and (
                    item.suffix in {".eml", ".pdf", ".txt"} or item.name == "live-run-results.json"
                ):
                    item.unlink()
        target.mkdir(parents=True, exist_ok=True)

    case = rows(db, "select * from cases")[0]
    client = json.loads(rows(db, "select context from loans")[0]["context"])["client_configuration"]
    brand = client["display_name"]
    result = json.loads((source / "results.json").read_text())["cases"][0]
    run_start = moment(result["runs"][0]["checkpoint"]["started_at"])
    received = moment(case["original_received_at"])

    def business_time(created: str, initial: bool = False) -> datetime:
        if initial:
            return received.astimezone(EASTERN)
        return (fixture.evaluation_at + (moment(created) - run_start)).astimezone(EASTERN)

    evidence = {e["id"]: e for e in rows(db, "select * from evidence")}
    messages = rows(db, "select * from mail_messages order by created_at")
    deliveries = rows(db, "select * from outbox_entries order by created_at")
    subject = messages[0]["subject"] if messages else fixture.title
    events = [("in", m["created_at"], m) for m in messages] + [
        ("out", d["created_at"], d) for d in deliveries
    ]
    events.sort(key=lambda e: e[1])

    thread, number = [], 0
    for index, (direction, created, row) in enumerate(events):
        number += 1
        when = business_time(created, initial=index == 0 and direction == "in")
        mail = EmailMessage()
        if direction == "in":
            mail["From"] = f"{fixture.borrower_display_name} <{row['sender']}>"
            mail["To"] = f"{brand} <{row['recipient'] or SERVICE_ADDRESS}>"
            mail["Subject"] = row["subject"]
            body = row["body"]
            attached = [
                (a["title"], evidence.get(a.get("evidence_id"), {}).get("storage_key"))
                for a in json.loads(row["attachments"] or "[]")
            ]
            kind = "request" if index == 0 else "reply"
        else:
            sent = json.loads(row["sent_content"])
            mail["From"] = f"{brand} <{sent['sender']}>"
            mail["To"] = f"{fixture.borrower_display_name} <{sent['recipient']}>"
            mail["Subject"] = f"RE: {subject}"
            body = sent["body"]
            attached = [(a["title"], a["storage_key"]) for a in sent.get("attachments", [])]
            kind = "response"
        mail["Date"] = format_datetime(when)
        mail.set_content(body)
        files = []
        for title, key in attached:
            if key and (docs / key).is_file():
                name = f"{slug(title)}.pdf"
                mail.add_attachment(
                    (docs / key).read_bytes(),
                    maintype="application",
                    subtype="pdf",
                    filename=name,
                )
                files.append(name)
        name = f"{number:02}-{'inbound' if direction == 'in' else 'outbound'}-{kind}.eml"
        (out / "correspondence" / name).write_bytes(bytes(mail))
        thread.append(
            {
                "direction": direction,
                "file": name,
                "from": mail["From"],
                "to": mail["To"],
                "subject": mail["Subject"],
                "when": when,
                "attachments": files,
                "body": body,
                "reference": row.get("delivery_reference"),
            }
        )

    notes = rows(db, "select * from final_notes order by created_at")
    number += 1
    notes_file = f"{number:02}-servicing-notes.txt"
    (out / "correspondence" / notes_file).write_text(
        "\n\n----------\n\n".join(n["content"] for n in notes) + "\n"
    )

    for row in evidence.values():
        if row["storage_key"] and (docs / row["storage_key"]).is_file():
            shutil.copy(
                docs / row["storage_key"],
                out / "documents" / f"{slug(row['title'])}.pdf",
            )
    packages = rows(db, "select * from indexed_packages order by created_at")
    for index, row in enumerate(packages, 1):
        fields = json.loads(row["index_fields"])
        name = f"indexed-package-{index}-{slug(fields.get('correspondence_type', 'response'))}.pdf"
        shutil.copy(docs / fields["pdf_storage_key"], out / "documents" / name)

    drafts = rows(db, "select * from response_drafts order by version")
    reviews = rows(db, "select * from review_decisions order by created_at")
    sent_ids = {json.loads(d["sent_content"])["draft_id"] for d in deliveries}
    folder = out / "correspondence" / "drafts"
    if folder.exists():
        shutil.rmtree(folder)
    if len(drafts) > len(deliveries):
        folder.mkdir()
        for draft in drafts:
            (folder / f"draft-v{draft['version']}.txt").write_text(draft["body"] + "\n")

    def cell(text):
        return text.replace('"', "").replace("<", "&lt;").replace(">", "&gt;")

    lines = [f"# Correspondence thread — loan {fixture.loan_identifier}", ""]
    for index, item in enumerate(thread, 1):
        heading = "Inbound" if item["direction"] == "in" else "Outbound response (live agent run)"
        lines += [
            f"## {index}. {heading}",
            "",
            "| | |",
            "|---|---|",
            f"| From | {cell(item['from'])} |",
            f"| To | {cell(item['to'])} |",
            f"| Date | {item['when'].strftime('%A, %B %-d, %Y, %-I:%M %p')} ET |",
            f"| Subject | {item['subject']} |",
            f"| Attachments | {', '.join(item['attachments']) or 'None'} |",
            *([f"| Delivery reference | {item['reference']} |"] if item["reference"] else []),
            f"| File | `{item['file']}` |",
            "",
            "```text",
            item["body"],
            "```",
            "",
        ]
    if folder.exists():
        by_id = {d["id"]: d["version"] for d in drafts}
        lines += [
            "## Response versions and reviews",
            "",
            "| Version | Prepared | Origin | Review | Sent | Text |",
            "|---|---|---|---|---|---|",
        ]
        for draft in drafts:
            validation = json.loads(draft["validation"] or "{}")
            origin = (
                f"Reviewer edit of v{by_id.get(validation['edited_from'], '?')}"
                if validation.get("edited_from")
                else "Agent"
            )
            decided = "; ".join(
                f"{r['decision']} by {r['actor']}: {r['note']}"
                for r in reviews
                if r["draft_id"] == draft["id"]
            )
            lines.append(
                f"| {draft['version']} | "
                f"{business_time(draft['created_at']).strftime('%b %-d, %-I:%M:%S %p')} ET | "
                f"{origin} | {cell(decided) or 'None'} | "
                f"{'Yes' if draft['id'] in sent_ids else 'No'} | "
                f"`drafts/draft-v{draft['version']}.txt` |"
            )
        lines.append("")
    lines += [
        f"## {len(thread) + 1}. Servicing notes (ILS, Standout Comment)",
        "",
        (
            f"`{notes_file}` holds {len(notes)} note(s), one per delivery. Each repeats the "
            "delivered text under the delivery reference."
        ),
        "",
    ]
    (out / "correspondence" / "README.md").write_text("\n".join(lines))

    rehearsal = {
        "recorded_on": datetime.now(EASTERN).date().isoformat(),
        "deployment": args.deployment,
    }
    for label, folder in (("api_path", args.api), ("mailbox_path", args.mailbox)):
        if folder:
            path = ROOT / folder
            rehearsal[label] = run_record(
                path,
                label.split("_")[0],
                sqlite3.connect(path / "correspondence.sqlite3"),
            )
    (out / "rehearsal" / "live-run-results.json").write_text(
        json.dumps(rehearsal, indent=2, ensure_ascii=False) + "\n"
    )
    print(f"Wrote {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--out", required=True, help="Pack folder, e.g. usecases/demo-3-tax")
    parser.add_argument("--mailbox", help="Mailbox evaluation folder (preferred source)")
    parser.add_argument("--api", help="API evaluation folder (rehearsal numbers)")
    parser.add_argument("--deployment", default="gpt-5.6-sol")
    args = parser.parse_args()
    if not (args.mailbox or args.api):
        parser.error("Supply --mailbox and/or --api")
    build(args)


if __name__ == "__main__":
    main()
