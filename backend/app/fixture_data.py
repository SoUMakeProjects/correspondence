from app.domain import DomainError
from app.fixture_contracts import FollowupFixture, ScenarioFixture
from app.source_catalog import DATA_ROOT, read_json

SCENARIOS = ("DEMO-01", "DEMO-02", "DEMO-03", "DEMO-04", "DEMO-05")


def variants_for(scenario_id: str) -> list[str]:
    if scenario_id not in SCENARIOS:
        raise DomainError(
            404, "scenario_not_found", "Choose one of the five available demo scenarios."
        )
    if scenario_id == "DEMO-02":
        return ["base", "missing_document", "unreadable_document", "wrong_loan"]
    return ["base", "followup"]


def load_fixture(scenario_id: str, variant: str = "base") -> ScenarioFixture:
    if variant not in variants_for(scenario_id):
        raise DomainError(
            422, "variant_not_available", "This variant is not available for the scenario."
        )
    data = read_json(DATA_ROOT / "fixtures/v1" / f"{scenario_id}.json")
    if variant == "followup":
        followup = FollowupFixture.model_validate(
            read_json(DATA_ROOT / "presenter/v1" / f"{scenario_id}.json")
        )
        if followup.scenario_id != scenario_id:
            raise ValueError("Prepared follow-up belongs to another scenario.")
        for field in ("documents", "tasks"):
            indexed = {row["key"]: row for row in data[field]}
            indexed.update(
                {row.key: row.model_dump(mode="json") for row in getattr(followup, field)}
            )
            data[field] = list(indexed.values())
        data["loan_context"].update(followup.loan_context_patch)
    elif variant != "base":
        document = data["documents"][0]
        if variant == "wrong_loan":
            document["declared_loan_identifier"] = "0099000099"
        else:
            document["availability"] = "missing" if variant == "missing_document" else "unreadable"
    return ScenarioFixture.model_validate(data)


def scenario_catalog() -> list[dict]:
    result = []
    for key in SCENARIOS:
        item = load_fixture(key)
        result.append(
            {
                "scenario_id": key,
                "version": item.version,
                "title": item.title,
                "family": item.family,
                "client_code": item.client_code,
                "variants": variants_for(key),
            }
        )
    return result
