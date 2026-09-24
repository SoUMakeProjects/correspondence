"""The model-facing observation drops repeats without losing information."""

import json

from test_phase4 import act, prepare
from test_phase7 import load, new_response, supply

from app.agent_model import AzureModel
from app.agent_tools import observe
from app.model_view import OMITTED, REFERENCE, _strip, expand, model_view


def name_change_after_update(client):
    case = load(client, "DEMO-01")
    interim = prepare(client, case, "information_request")
    for operation in ("csp.send", "onbase.index", "ils.final_note"):
        act(client, case, operation, draft_id=interim)
    supply(client, case, "name_legal_document")
    task, _ = act(client, case, "ils.create_task", task_type="demo_profile_name_update")
    act(client, case, "ils.update_name", task_id=task["reference"]["id"])
    final = new_response(client, case)
    for operation in ("csp.send", "onbase.index", "ils.final_note"):
        act(client, case, operation, draft_id=final)
    return case


def observation_for(application, settings, case):
    with application.state.sessions() as session:
        return observe(session, settings.data_dir, case["id"])


def test_view_is_smaller_and_expands_to_the_same_content(client, application, settings):
    case = name_change_after_update(client)
    observation = observation_for(application, settings, case)
    view = model_view(observation)
    assert len(json.dumps(view)) < 0.8 * len(json.dumps(observation))

    stripped, expanded = _strip(observation), expand(view)
    # The embedded client configuration is a flattened copy of the client record.
    client_record = expanded["loan"]["context"]["client_configuration"]
    assert stripped["loan"]["context"]["client_configuration"] == {
        "code": client_record["code"],
        "version": client_record["version"],
        "display_name": client_record["display_name"],
        **client_record["settings"],
    }
    for document in (stripped, expanded):
        for context in [document["loan"]["context"]] + [
            e["details"].get("facts") or {} for e in document["evidence"]
        ]:
            context.pop("client_configuration", None)
    assert expanded == stripped


def test_only_known_repeats_are_referenced_and_decision_sections_stay_verbatim(
    client, application, settings
):
    case = name_change_after_update(client)
    observation = observation_for(application, settings, case)
    view = model_view(observation)
    text = json.dumps(view)
    assert not any(f'"{key}"' in text for key in OMITTED)
    record = next(e for e in view["evidence"] if e["title"] == "Synthetic servicing record")
    assert record["details"]["facts"] == {REFERENCE: "loan.context"}
    assert view["loan"]["context"]["client_configuration"] == {REFERENCE: "client"}
    assert view["related_cases"] == [{REFERENCE: "case"}]
    for key in ("assessment", "handoffs", "saved", "tasks", "client"):
        assert view[key] == _strip(observation[key])
    assert view["case"] == _strip(observation["case"])


def test_azure_request_carries_the_compact_view(client, application, settings):
    case = name_change_after_update(client)
    observation = observation_for(application, settings, case)
    captured = {}

    class Capture(AzureModel):
        def complete(self, payload, timeout):
            captured.update(payload)

    Capture(settings).choose(observation, [], 30)
    content = json.loads(captured["messages"][-1]["content"])
    assert content["observed_data"] == json.loads(json.dumps(model_view(observation)))
