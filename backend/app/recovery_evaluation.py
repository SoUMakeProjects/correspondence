"""Explicit live Azure recovery evaluation against isolated local simulators."""

import argparse
import json
import time
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import utcnow
from app.main import create_app


def evaluate(settings):
    root = settings.data_dir / "recovery-evaluations" / str(uuid4())
    report = {
        "source": "live_azure",
        "created_at": utcnow().isoformat(),
        "status": "running",
        "cases": [],
    }

    def persist():
        (root / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    with TestClient(create_app(settings.model_copy(update={"app_data_dir": root}))) as client:

        def get(path):
            result = client.get("/api" + path)
            result.raise_for_status()
            return result.json()

        def post(path, payload):
            result = client.post("/api" + path, json=payload)
            result.raise_for_status()
            return result.json()

        for fault in ("index_failure", "unknown_send_status"):
            case = post(
                "/scenarios/DEMO-02/instances", {"request_id": str(uuid4()), "variant": "base"}
            )
            prefix = f"/cases/{case['id']}"
            record = {"case_id": case["id"], "fault": fault, "runs": [], "checks": {}}
            report["cases"].append(record)

            def run(**values):
                started = post(
                    prefix + "/runs", {"expected_revision": get(prefix)["revision"], **values}
                )
                record["runs"].append(started)
                step = -1
                deadline = time.monotonic() + settings.agent_max_seconds + 60
                while started["status"] in {"running", "queued"} and time.monotonic() < deadline:
                    time.sleep(0.5)
                    started = get(f"/runs/{started['id']}")
                    record["runs"][-1] = started
                    if started["checkpoint"]["steps"] != step:
                        step = started["checkpoint"]["steps"]
                        print(
                            json.dumps(
                                {
                                    "fault": fault,
                                    "run_id": started["id"],
                                    "step": step,
                                    "status": started["status"],
                                }
                            ),
                            flush=True,
                        )
                    persist()
                return started

            def control(path, **values):
                return post(
                    prefix + "/recovery/" + path,
                    {
                        "request_id": str(uuid4()),
                        "expected_revision": get(prefix)["revision"],
                        "actor": "Live evaluation presenter",
                        **values,
                    },
                )

            try:
                first = run(fault=fault)
                assert first["status"] == "waiting_for_input"
                before = get(prefix + "/artifacts")
                assert len(before["outbox"]) == 1 and not before["packages"]
                record["checks"]["paused_after_delivery"] = True
                if fault == "unknown_send_status":
                    state = get(prefix + "/recovery")
                    assert state["blocked"] and state["actions"][0]["outcome"] == "unknown"
                    assert control("check")["blocked"]
                    record["checks"]["unknown_not_retried"] = (
                        len(get(prefix + "/artifacts")["outbox"]) == 1
                    )
                    control("restore-status", action_id=state["actions"][0]["id"])
                    assert not control("check")["blocked"]
                final = run(resume_from=first["id"])
                after = get(prefix + "/artifacts")
                record["checks"].update(
                    live_model=all(
                        r["model_configuration"]["source"] == "live_azure" for r in record["runs"]
                    ),
                    completed=final["status"] == "completed" and get(prefix)["status"] == "closed",
                    no_resend=after["outbox"] == before["outbox"],
                    one_package_and_note=len(after["packages"]) == len(after["notes"]) == 1,
                    linked_resume=final["checkpoint"]["resumed_from"] == first["id"],
                    original_receipt=get(prefix)["original_received_at"]
                    == case["original_received_at"],
                    completion_valid=get(prefix + "/completion-check")["valid"],
                )
                record["summary"] = get(f"/runs/{final['id']}/summary")
                record["export"] = get(f"/runs/{final['id']}/export")
                record["status"] = "passed" if all(record["checks"].values()) else "failed"
            except Exception as exc:
                record["status"], record["error"] = "failed", type(exc).__name__
            persist()
            print(
                json.dumps(
                    {"fault": fault, "status": record["status"], "checks": record["checks"]}
                ),
                flush=True,
            )
            if record["status"] == "failed":
                break
    report["status"] = (
        "passed"
        if len(report["cases"]) == 2 and all(c["status"] == "passed" for c in report["cases"])
        else "failed"
    )
    persist()
    (settings.data_dir / "phase8-live-latest.json").write_text(
        json.dumps({"status": report["status"], "path": str(root / "results.json")}, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps({"status": report["status"], "report": str(root / "results.json")}), flush=True
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    if not args.live or settings.missing_azure_fields:
        parser.error("Supply --live and complete Azure configuration; no requests were made.")
    raise SystemExit(0 if evaluate(settings)["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
