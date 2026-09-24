"""Explicit deterministic development demonstration, without an AI run."""

import argparse
import json
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4


def run(base_url):
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1"}
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Use the local application HTTP URL.")
    base_url = base_url.rstrip("/")

    def request(path, payload=None):
        req = Request(
            base_url + "/api" + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req, timeout=30) as response:
            return json.load(response)

    case = request("/scenarios/DEMO-02/instances", {"request_id": str(uuid4()), "variant": "base"})
    prefix = f"/cases/{case['id']}"
    path = f"/simulations/{case['simulation_id']}/cases/{case['id']}/tools"
    results = []

    def action(operation, **args):
        current = request(prefix)
        assessment = request(prefix + "/assessment")
        result = request(
            path,
            {
                "loan_identifier": case["loan_identifier"],
                "client_code": case["client_code"],
                "command": {
                    "operation": operation,
                    "action_id": str(uuid4()),
                    "expected_revision": current["revision"],
                    "input_hash": assessment["input_hash"],
                    "evidence_versions": assessment["evidence_versions"],
                    **args,
                },
            },
        )
        if result["status"] != "simulated_complete":
            raise RuntimeError(f"{operation}: {result['code']}: {result['message']}")
        results.append(
            {"operation": operation, "status": result["status"], "reference": result["reference"]}
        )
        return result

    action("cct.apply_plan")
    current = request(prefix)
    assessment = request(prefix + "/assessment")
    evidence = request(prefix + "/evidence")
    record = next(e for e in evidence if e["details"]["kind"] == "record")
    document = next(e for e in evidence if e["details"].get("key") == "amortization")
    context = record["details"]["facts"]
    config = context["client_configuration"]
    candidate = {
        "case_revision": current["content_revision"],
        "version": 1,
        "response_type": "final_resolution",
        "client_code": case["client_code"],
        "client_version": config["version"],
        "sender": config["sender_email"],
        "recipient": context["authorized_recipient"],
        "evidence_versions": assessment["evidence_versions"],
        "attachment_ids": [document["id"]],
        "disclosure_ids": config["disclosure_keys"],
        "concerns": [
            {"concern_id": c["concern_id"], "disposition": c["disposition"]}
            for c in assessment["concerns"]
        ],
        "claims": [
            {
                "field": "document_attached",
                "value": document["title"],
                "evidence_id": document["id"],
            }
        ],
    }
    draft = action("csp.prepare", candidate=candidate)["reference"]["id"]
    action("csp.send", draft_id=draft)
    package = action("onbase.index", draft_id=draft)["reference"]["id"]
    action("ils.final_note", draft_id=draft)
    action("cct.close", draft_id=draft)
    return {
        "mode": "deterministic_development_demo",
        "simulated": True,
        "case_id": case["id"],
        "simulation_id": case["simulation_id"],
        "status": request(prefix)["status"],
        "actions": results,
        "package_url": base_url
        + f"/api/simulations/{case['simulation_id']}/cases/{case['id']}/packages/{package}/file?loan_identifier={case['loan_identifier']}&client_code={case['client_code']}",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    print(json.dumps(run(args.base_url), indent=2))


if __name__ == "__main__":
    main()
