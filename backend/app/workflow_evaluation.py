"""Live five-family evaluation with explicit simulated presenter interventions."""

import argparse
import json
import re
import time
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import utcnow
from app.main import create_app


def evaluate(settings, scenarios, *, mailbox=False):
    root = (
        settings.data_dir
        / ("mailbox-evaluations" if mailbox else "workflow-evaluations")
        / str(uuid4())
    )
    isolated = settings.model_copy(update={"app_data_dir": root})
    result = {
        "source": "live_azure",
        "checked_at": utcnow().isoformat(),
        "cases": [],
        "status": "running",
        "automatic_mailbox": mailbox,
    }
    with TestClient(create_app(isolated)) as client:

        def post(path, payload):
            response = client.post("/api" + path, json=payload)
            response.raise_for_status()
            return response.json()

        def get(path):
            response = client.get("/api" + path)
            response.raise_for_status()
            return response.json()

        def persist():
            (root / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

        for scenario in scenarios:
            if mailbox:
                message = post(
                    "/mail/messages", {"request_id": str(uuid4()), "template_key": scenario}
                )
                deadline = time.monotonic() + 45
                thread = get(f"/mail/threads/{message['thread_id']}")
                while not thread["thread"]["case_id"] and time.monotonic() < deadline:
                    time.sleep(0.5)
                    thread = get(f"/mail/threads/{message['thread_id']}")
                case = get(f"/cases/{thread['thread']['case_id']}")
            else:
                case = post(
                    f"/scenarios/{scenario}/instances",
                    {"request_id": str(uuid4()), "variant": "base"},
                )
            prefix = f"/cases/{case['id']}"
            record = {
                "scenario": scenario,
                "case_id": case["id"],
                "simulation_id": case["simulation_id"],
                "runs": [],
                "interventions": [],
                "checks": {},
            }
            result["cases"].append(record)

            def run():
                previous = record["runs"][-1] if record["runs"] else None
                payload = {"expected_revision": get(prefix)["revision"]}
                if previous and previous["status"] in {"waiting_for_input", "waiting_for_review"}:
                    payload["resume_from"] = previous["id"]
                if mailbox:
                    deadline = time.monotonic() + 45
                    runs = get(prefix + "/runs")
                    while len(runs) <= len(record["runs"]) and time.monotonic() < deadline:
                        time.sleep(0.5)
                        runs = get(prefix + "/runs")
                    if len(runs) <= len(record["runs"]):
                        raise RuntimeError("The case event did not automatically start a run.")
                    started = runs[len(record["runs"])]
                    assert started["checkpoint"].get("trigger_ids")
                else:
                    started = post(prefix + "/runs", payload)
                record["runs"].append(started)
                print(
                    json.dumps(
                        {
                            "scenario": scenario,
                            "run_id": started["id"],
                            "stage": len(record["runs"]),
                        }
                    ),
                    flush=True,
                )
                deadline, step = time.monotonic() + settings.agent_max_seconds + 75, -1
                while started["status"] in {"queued", "running"} and time.monotonic() < deadline:
                    time.sleep(0.5)
                    started = get(f"/runs/{started['id']}")
                    record["runs"][-1] = started
                    if started["checkpoint"]["steps"] != step:
                        step = started["checkpoint"]["steps"]
                        history = started["checkpoint"]["history"]
                        if history:
                            print(
                                json.dumps(
                                    {k: history[-1][k] for k in ("step", "tool", "status", "code")}
                                ),
                                flush=True,
                            )
                    persist()
                print(
                    json.dumps(
                        {
                            "scenario": scenario,
                            "status": started["status"],
                            "reason": started["checkpoint"].get("reason"),
                        }
                    ),
                    flush=True,
                )
                if started["status"] in {"running", "queued", "failed", "stopped"} or started[
                    "checkpoint"
                ].get("reason") not in {"verified_outcome", "review_required", "verified_handoff"}:
                    raise RuntimeError(
                        "Live run did not reach a supported workflow outcome; inspect its retained report."
                    )
                return started

            def supply(kind, **values):
                if mailbox and kind in {"name_legal_document", "eft_clarification"}:
                    post(
                        "/mail/messages",
                        {
                            "request_id": str(uuid4()),
                            "thread_id": message["thread_id"],
                            "template_key": "name-proof"
                            if kind == "name_legal_document"
                            else "eft-outgoing_refund",
                        },
                    )
                    record["interventions"].append({"kind": "borrower_email", "input": kind})
                    return
                post(
                    prefix + "/inputs",
                    {
                        "request_id": str(uuid4()),
                        "expected_revision": get(prefix)["revision"],
                        "kind": kind,
                        "actor": "Demo evaluation presenter",
                        **values,
                    },
                )
                record["interventions"].append({"kind": kind})

            def review(edit=False):
                draft = get(prefix + "/workflow")["drafts"][-1]
                if edit:
                    candidate = draft["candidate"]
                    args = {
                        k: candidate[k]
                        for k in ("response_type", "concerns", "claims", "attachment_ids")
                    }
                    # A real reviewer edit: include the independently verified due date if absent.
                    evidence = next(
                        e for e in get(prefix + "/evidence") if e["details"]["kind"] == "record"
                    )
                    if scenario == "DEMO-03" and not any(
                        c["field"] == "tax_due_date" for c in args["claims"]
                    ):
                        args["claims"].append(
                            {
                                "field": "tax_due_date",
                                "value": evidence["details"]["facts"]["tax_due_date"],
                                "evidence_id": evidence["id"],
                            }
                        )
                    post(
                        prefix + "/draft-edits",
                        {
                            "request_id": str(uuid4()),
                            "expected_revision": get(prefix)["revision"],
                            "draft_id": draft["id"],
                            "draft_version": draft["version"],
                            **values_for_actor(),
                            **args,
                        },
                    )
                    draft = get(prefix + "/workflow")["drafts"][-1]
                    record["interventions"].append(
                        {"kind": "validated_draft_edit", "draft_id": draft["id"]}
                    )
                assert draft["current"] and not draft["sent"]
                post(
                    prefix + "/reviews",
                    {
                        "request_id": str(uuid4()),
                        "expected_case_revision": get(prefix)["revision"],
                        "draft_id": draft["id"],
                        "draft_version": draft["version"],
                        "decision": "approve",
                        "note": {
                            "DEMO-03": "Reviewed current facts and evidence; scheduled is not paid.",
                            "DEMO-04": "Reviewed: counsel-only recipient, receipt and referral "
                            "only; no credit reporting outcome stated.",
                        }.get(scenario, "Reviewed current facts and evidence."),
                        **values_for_actor(),
                    },
                )
                record["interventions"].append({"kind": "review_approved", "draft_id": draft["id"]})

            def settle():
                latest = record["runs"][-1]
                for _ in range(2):
                    if latest["status"] != "waiting_for_review":
                        return latest
                    review()
                    latest = run()
                return latest

            try:
                first = run()
                if scenario == "DEMO-01":
                    settle()
                    record["checks"]["initial_missing_request"] = get(prefix)[
                        "status"
                    ] == "waiting_for_borrower" and bool(get(prefix + "/artifacts")["outbox"])
                    supply("name_legal_document")
                    run()
                    settle()
                elif scenario == "DEMO-03":
                    assert first["status"] == "waiting_for_review"
                    supply("tax_specialist_result")
                    record["checks"]["old_draft_invalidated"] = not get(prefix + "/workflow")[
                        "drafts"
                    ][0]["current"]
                    run()
                    review(edit=True)
                    run()
                elif scenario == "DEMO-04":
                    settle()
                    record["checks"]["initial_handoff"] = bool(
                        get(prefix + "/workflow")["handoffs"]
                    )
                    record["checks"]["acknowledgment_sent_before_determination"] = bool(
                        get(prefix + "/artifacts")["outbox"]
                    )
                    supply("bankruptcy_specialist_result")
                    run()
                    settle()
                    handoff = next(
                        h for h in reversed(get(prefix + "/workflow")["handoffs"]) if h["current"]
                    )
                    post(
                        prefix + "/handoff-acknowledgments",
                        {
                            "request_id": str(uuid4()),
                            "expected_revision": get(prefix)["revision"],
                            "handoff_id": handoff["id"],
                            "actor": "Compliance – credit reporting disputes",
                        },
                    )
                    record["interventions"].append({"kind": "handoff_acknowledged"})
                    run()
                elif scenario == "DEMO-05":
                    settle()
                    record["checks"]["initial_clarification_requested"] = bool(
                        get(prefix + "/artifacts")["outbox"]
                    )
                    supply("eft_clarification", eft_intent="outgoing_refund")
                    run()
                    settle()
                else:
                    settle()
                current = get(prefix)
                saved = get(prefix + "/artifacts")
                assessment = get(prefix + "/assessment")
                tasks = get(prefix + "/tasks")
                expected = {
                    "DEMO-01": "waiting_on_department",
                    "DEMO-02": "closed",
                    "DEMO-03": "closed",
                    "DEMO-04": "transferred",
                    "DEMO-05": "waiting_for_borrower",
                }[scenario]
                checks = record["checks"]
                checks.update(
                    expected_case_status=current["status"] == expected,
                    receipt_anchor_preserved=current["original_received_at"]
                    == case["original_received_at"],
                    all_runs_live=all(
                        r["model_configuration"]["source"] == "live_azure" for r in record["runs"]
                    ),
                    claims_validated=all(
                        d["validation"]["report"]["valid"] for d in saved["drafts"]
                    ),
                    no_duplicate_delivery=len(saved["outbox"])
                    == len({e["draft_id"] for e in saved["outbox"]}),
                )
                if mailbox:
                    checks["all_runs_automatically_triggered"] = all(
                        r["checkpoint"].get("trigger_ids") for r in record["runs"]
                    )
                    connected = get(f"/systems/cases/{case['id']}")
                    conversation = get(f"/mail/threads/{message['thread_id']}")
                    checks["same_records_in_system_views"] = (
                        connected["outbox"] == saved["outbox"]
                        and connected["packages"] == saved["packages"]
                    )
                    checks["mailbox_contains_actual_responses"] = (
                        conversation["deliveries"] == saved["outbox"]
                    )
                    checks["reply_stays_in_original_case"] = (
                        conversation["thread"]["case_id"] == case["id"]
                    )
                if expected == "closed":
                    checks["completion_verified"] = get(prefix + "/completion-check")["valid"]
                if scenario in {"DEMO-01", "DEMO-03", "DEMO-04"}:
                    checks["single_task_reused"] = len(tasks) == 1
                if scenario == "DEMO-01":
                    checks["actual_name_update"] = (
                        tasks[0]["status"] == "completed"
                        and "Lauren E. Castellano" in saved["drafts"][-1]["body"]
                    )
                    checks["classification_handoff_retained"] = assessment[
                        "classification"
                    ] is None and any(h["current"] for h in get(prefix + "/workflow")["handoffs"])
                    checks["both_responses_retained"] = all(
                        len(saved[key]) == 2 for key in ("outbox", "packages", "notes")
                    )
                if scenario == "DEMO-03":
                    letter = saved["outbox"][-1]["sent_content"]["body"] if saved["outbox"] else ""
                    checks["single_delivery"] = len(saved["outbox"]) == 1
                    checks["scheduled_not_paid"] = (
                        "has not been paid yet" in letter
                        and "Payment status: Scheduled (not yet paid)" in letter
                        and "Payment status: Paid" not in letter
                    )
                    checks["tax_team_result_cited"] = "Tax Team review reference:" in letter
                    checks["due_date_in_letter"] = "Due date: October 30, 2026" in letter
                if scenario == "DEMO-04":
                    counsel = "monica.ferrante@ferrantehale.example.com"
                    checks["classification_exception_retained"] = (
                        assessment["classification"] is None
                    )
                    checks["representative_only"] = assessment[
                        "authorized_recipient"
                    ] == counsel and all(
                        e["sent_content"]["recipient"] == counsel for e in saved["outbox"]
                    )
                    letters = [e["sent_content"]["body"] for e in saved["outbox"]]
                    checks["single_acknowledgment"] = len(letters) == 1 and bool(
                        "It is not the result of our investigation." in letters[0]
                        and "Written response by: October 21, 2026" in letters[0]
                    )
                    checks["no_reporting_outcome_stated"] = not any(
                        re.search(
                            r"(has|have) been (corrected|removed|deleted)|we (corrected|"
                            r"removed|deleted|will correct|will remove|will delete)",
                            body,
                            re.IGNORECASE,
                        )
                        for body in letters
                    )
                    checks["borrower_not_contacted"] = all(
                        "greg.lindqvist@outlook.com" not in json.dumps(e["sent_content"])
                        for e in saved["outbox"]
                    )
                    checks["final_run_transferred"] = (
                        record["runs"][-1]["checkpoint"].get("reason") == "verified_handoff"
                    )
                    handoffs = get(prefix + "/workflow")["handoffs"]
                    checks["determination_routed_to_compliance"] = any(
                        h["current"]
                        and h["status"] == "acknowledged"
                        and "Bankruptcy Team determination BK-REV-260922-004"
                        in (h.get("routing_note") or "")
                        for h in handoffs
                    )
                if scenario == "DEMO-05":
                    checks["consent_still_required"] = any(
                        f["code"] == "eft_authorization_required" for f in assessment["findings"]
                    )
                    letters = [e["sent_content"]["body"] for e in saved["outbox"]]
                    checks["two_borrower_letters"] = len(letters) == 2
                    checks["clarification_explains_meanings"] = bool(
                        letters and "one of three different things" in letters[0]
                    )
                    checks["refund_authorization_requested"] = bool(
                        len(letters) > 1
                        and "Electronic Refund Authorization" in letters[-1]
                        and "No money will move until" in letters[-1]
                    )
                    checks["no_funds_moved"] = not any(
                        phrase in body
                        for body in letters
                        for phrase in ("has been sent", "has been deposited", "we sent")
                    )
                record["case_status"] = current["status"]
                record["inspection"] = get(f"/simulations/{case['simulation_id']}")
                record["status"] = "passed" if all(checks.values()) else "failed"
            except Exception as exc:
                record["status"] = "failed"
                record["error"] = type(exc).__name__
                result["status"] = "failed"
                persist()
                print(
                    json.dumps({"status": "failed", "report": str(root / "results.json")}),
                    flush=True,
                )
                return result
            persist()
            print(json.dumps({"scenario": scenario, "checks": record["checks"]}), flush=True)
    result["status"] = (
        "passed" if all(c["status"] == "passed" for c in result["cases"]) else "failed"
    )
    persist()
    (
        settings.data_dir / ("mailbox-live-latest.json" if mailbox else "phase7-live-latest.json")
    ).write_text(
        json.dumps({"status": result["status"], "path": str(root / "results.json")}, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps({"status": result["status"], "report": str(root / "results.json")}), flush=True
    )
    return result


def values_for_actor():
    return {"actor": "Demo evaluation reviewer"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--mailbox", action="store_true", help="Trigger every run using mail and human decisions."
    )
    parser.add_argument(
        "--scenario",
        choices=["all", "DEMO-01", "DEMO-02", "DEMO-03", "DEMO-04", "DEMO-05"],
        default="all",
    )
    args = parser.parse_args()
    settings = Settings()
    if not args.live or settings.missing_azure_fields:
        parser.error("Supply --live and complete Azure configuration; no calls were made.")
    selected = [f"DEMO-0{i}" for i in range(1, 6)] if args.scenario == "all" else [args.scenario]
    raise SystemExit(
        0 if evaluate(settings, selected, mailbox=args.mailbox)["status"] == "passed" else 1
    )


if __name__ == "__main__":
    main()
