"""Explicit, bounded Azure tool-call verification using only synthetic read access."""

import argparse
import json
import re
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from app.config import Settings
from app.repository import fingerprint


def configuration_fingerprint(settings):
    return fingerprint(
        {
            "base_url": settings.azure_openai_base_url,
            "deployment": settings.azure_openai_deployment,
            "key": settings.azure_openai_api_key.get_secret_value(),
        }
    )


def last_check(settings):
    path = settings.data_dir / "azure-live-check.json"
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(report, dict) and report.get(
            "configuration_fingerprint"
        ) == configuration_fingerprint(settings):
            return report
    except (OSError, ValueError):
        pass
    return None


class ProbeError(Exception):
    pass


def completion(settings, payload):
    request = Request(
        settings.azure_openai_base_url + "chat/completions",
        data=json.dumps({"model": settings.azure_openai_deployment, **payload}).encode(),
        headers={
            "Content-Type": "application/json",
            "api-key": settings.azure_openai_api_key.get_secret_value(),
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=min(settings.azure_openai_timeout_seconds, 60)) as response:
            return json.load(response)
    except HTTPError as exc:
        try:
            error = json.loads(exc.read()).get("error", {})
            code = re.sub(r"[^A-Za-z0-9_.-]", "", str(error.get("code", "request_rejected")))[:80]
            parameter = error.get("param")
            suffix = (
                f" ({parameter})"
                if parameter
                in {
                    "max_completion_tokens",
                    "tools",
                    "tool_choice",
                    "parallel_tool_calls",
                    "response_format",
                }
                else ""
            )
        except (ValueError, AttributeError):
            code, suffix = "request_rejected", ""
        raise ProbeError(f"Azure HTTP {exc.code}: {code}{suffix}") from None
    except (URLError, TimeoutError, OSError):
        raise ProbeError("Azure connectivity or request timeout failure.") from None


def run(settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    if settings.missing_azure_fields:
        raise ProbeError("Required Azure configuration is incomplete.")
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "status": "failed",
        "requests": 0,
        "configuration_fingerprint": configuration_fingerprint(settings),
        "checks": {},
        "automatic_agent_enabled": False,
        "source": "live_azure",
        "usage": [],
    }
    probe_settings = settings.model_copy(
        update={"app_data_dir": settings.data_dir / "azure-probes" / str(uuid4())}
    )
    try:
        with TestClient(create_app(probe_settings)) as client:
            loaded = client.post(
                "/api/scenarios/DEMO-02/instances",
                json={"request_id": str(uuid4()), "variant": "base"},
            )
            loaded.raise_for_status()
            case = loaded.json()
            tool = {
                "type": "function",
                "function": {
                    "name": "cct_read",
                    "description": "Read the selected synthetic CCT case. No writes are permitted.",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {"case_id": {"type": "string"}},
                        "required": ["case_id"],
                        "additionalProperties": False,
                    },
                },
            }
            messages = [
                {
                    "role": "system",
                    "content": "Verify the selected synthetic case using cct_read. Use only returned tool facts. You cannot perform writes.",
                },
                {
                    "role": "user",
                    "content": f"Read synthetic case {case['id']}. After reading, return a JSON object containing only loan_identifier and status.",
                },
            ]
            report["requests"] += 1
            first = completion(
                settings,
                {
                    "messages": messages,
                    "tools": [tool],
                    "tool_choice": {"type": "function", "function": {"name": "cct_read"}},
                    "parallel_tool_calls": False,
                    "max_completion_tokens": 1024,
                },
            )
            report["usage"].append(
                {
                    k: first.get("usage", {}).get(k, 0)
                    for k in ("prompt_tokens", "completion_tokens", "total_tokens")
                }
            )
            message = first["choices"][0]["message"]
            calls = message.get("tool_calls", [])
            if (
                len(calls) != 1
                or calls[0]["function"]["name"] != "cct_read"
                or json.loads(calls[0]["function"]["arguments"]) != {"case_id": case["id"]}
            ):
                raise ProbeError("The deployment did not return the expected scoped function call.")
            report["checks"]["tool_call"] = True
            result = client.post(
                f"/api/simulations/{case['simulation_id']}/cases/{case['id']}/tools",
                json={
                    "loan_identifier": case["loan_identifier"],
                    "client_code": case["client_code"],
                    "command": {"operation": "cct.read"},
                },
            )
            result.raise_for_status()
            observed = result.json()["data"]["case"]
            facts = {"loan_identifier": observed["loan_identifier"], "status": observed["status"]}
            report["checks"]["scoped_simulator_read"] = True
            messages.extend(
                [
                    {"role": "assistant", "content": message.get("content"), "tool_calls": calls},
                    {"role": "tool", "tool_call_id": calls[0]["id"], "content": json.dumps(facts)},
                ]
            )
            report["requests"] += 1
            second = completion(
                settings,
                {
                    "messages": messages,
                    "response_format": {"type": "json_object"},
                    "max_completion_tokens": 1024,
                },
            )
            report["usage"].append(
                {
                    k: second.get("usage", {}).get(k, 0)
                    for k in ("prompt_tokens", "completion_tokens", "total_tokens")
                }
            )
            if json.loads(second["choices"][0]["message"]["content"]) != facts:
                raise ProbeError(
                    "The deployment's final answer did not match the returned tool facts."
                )
            report["checks"]["tool_result_used"] = True
            report["status"] = "passed"
    except ProbeError as exc:
        report["error"] = str(exc)
    except Exception:
        # Never dump raw provider responses, URLs, credentials, or SDK exceptions.
        report["error"] = (
            "The live check did not complete its expected protocol. Inspect the local implementation; provider payloads were not logged."
        )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "azure-live-check.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return {k: v for k, v in report.items() if k != "configuration_fingerprint"}


def main():
    parser = argparse.ArgumentParser(
        description="Run a live Azure tool-call check with synthetic read access only."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Explicitly authorize this bounded live check (up to two Azure requests).",
    )
    args = parser.parse_args()
    if not args.live:
        parser.error("Pass --live to make Azure requests. No requests were made.")
    try:
        report = run(Settings())
    except ProbeError as exc:
        print(str(exc))
        raise SystemExit(1) from None
    print(json.dumps(report, indent=2))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
