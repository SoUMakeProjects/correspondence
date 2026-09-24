"""Compact, lossless model-facing view of an agent observation.

Every model call resends the full case observation, so repeated content is paid for on each
call. The largest repeats are the loan context (copied into servicing-record and mail evidence),
the client configuration (copied into the loan context and those evidence copies) and the case
row (repeated as its own related case). This view replaces exactly those repeats with
``{"$same_as": "<path>"}`` and omits storage/idempotency fields the model cannot use.

The replacement is deliberately targeted. A generic "replace any repeated value" pass was tried
and cut about 40% of the observation, but it also referenced the assessment's concerns, routing
and findings, and in live EFT runs the model then consistently requested an unnecessary handoff.
Decision-guiding sections (assessment, case plan, handoffs, saved artifacts) are therefore left
verbatim. Server-side checks keep using the full observation; only the model prompt is compacted.
"""

import json

REFERENCE = "$same_as"
# Server bookkeeping: the model never supplies or reasons about these values.
OMITTED = {"creation_key", "creation_hash", "content_sha256", "storage_key"}
# Display-only text for the receiving team; the handoff's structured fields stay verbatim.
OMITTED |= {"routing_note", "acknowledgment_note"}


def _encoded(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _strip(value):
    if isinstance(value, dict):
        return {key: _strip(item) for key, item in value.items() if key not in OMITTED}
    if isinstance(value, list):
        return [_strip(item) for item in value]
    return value


def _is_client_copy(value, client) -> bool:
    """The loan context embeds a flattened copy of the client configuration."""
    return (
        isinstance(value, dict)
        and isinstance(client, dict)
        and value.get("code") == client.get("code")
        and value.get("version") == client.get("version")
        and value.get("display_name") == client.get("display_name")
        and _encoded(
            {k: v for k, v in value.items() if k not in {"code", "version", "display_name"}}
        )
        == _encoded(client.get("settings", {}))
    )


def _without_client_copy(context, client):
    if isinstance(context, dict) and _is_client_copy(context.get("client_configuration"), client):
        return {**context, "client_configuration": {REFERENCE: "client"}}
    return context


def model_view(observation: dict | None) -> dict | None:
    if not observation:
        return observation
    view = _strip(observation)
    client = view.get("client")
    loan = view.get("loan")
    if isinstance(loan, dict) and isinstance(loan.get("context"), dict):
        context = loan["context"]
        loan["context"] = _without_client_copy(context, client)
        for evidence in view.get("evidence") or []:
            details = evidence.get("details") or {}
            facts = details.get("facts")
            if facts == context:
                details["facts"] = {REFERENCE: "loan.context"}
            else:
                details["facts"] = _without_client_copy(facts, client)
    case = view.get("case")
    if case and isinstance(view.get("related_cases"), list):
        view["related_cases"] = [
            {REFERENCE: "case"} if row == case else row for row in view["related_cases"]
        ]
    return view


def expand(view, root=None):
    """Resolve every reference (used by tests to prove the view is lossless)."""
    root = view if root is None else root

    def lookup(path):
        value = root
        for part in path.split("."):
            value = value[part]
        return expand(value, root)

    if isinstance(view, dict):
        if set(view) == {REFERENCE}:
            return lookup(view[REFERENCE])
        return {key: expand(item, root) for key, item in view.items()}
    if isinstance(view, list):
        return [expand(item, root) for item in view]
    return view
