"""Validate versioned inputs without running a business workflow or model."""

import re
from collections import Counter
from io import BytesIO

from pypdf import PdfReader

from app.config import WORKSPACE_ROOT
from app.documents import library_document
from app.fixture_contracts import ClientFixture, KnowledgeFixture
from app.fixture_data import SCENARIOS, load_fixture, variants_for
from app.source_catalog import DATA_ROOT, read_json, reconcile_sources


def validate_data() -> dict:
    reconciled = reconcile_sources()
    for key, filename in (
        ("taxonomy", "taxonomy.v1.json"),
        ("manifest", "source_manifest.v1.json"),
        ("report", "reconciliation.v1.json"),
    ):
        if read_json(DATA_ROOT / "knowledge" / filename) != reconciled[key]:
            raise ValueError(
                f"Generated {key} differs from source reconciliation. Rebuild the data artifacts."
            )
    knowledge = [
        KnowledgeFixture.model_validate(row)
        for row in read_json(DATA_ROOT / "knowledge/curated.v1.json")
    ]
    clients = [
        ClientFixture.model_validate(row)
        for row in read_json(DATA_ROOT / "fixtures/v1/clients.json")
    ]
    if len({client.code for client in clients}) != 2 or len({row.key for row in knowledge}) != len(
        knowledge
    ):
        raise ValueError("Client and curated-content keys must be unique.")
    source_registry = read_json(DATA_ROOT / "knowledge/source_registry.v1.json")
    for reference in source_registry.values():
        path = (WORKSPACE_ROOT / reference["path"]).resolve()
        if not path.is_relative_to(WORKSPACE_ROOT) or not path.is_file():
            raise ValueError("Source registry reference is not an existing workspace file.")
    for item in knowledge:
        placeholders = re.findall(r"\{([a-z_]+)\}", item.content)
        if set(placeholders) != set(item.allowed_placeholders):
            raise ValueError("Template placeholders do not match the declared contract.")
        for reference in item.source_references:
            if reference.startswith("S04:r"):
                row = reconciled["manifest"][int(reference[5:]) - 2]
                if row["status"] == "excluded":
                    raise ValueError("Excluded content cannot supply curated guidance.")
            elif reference not in source_registry:
                raise ValueError("Curated item has an unknown source reference.")
    keys = {item.key for item in knowledge}
    policy = read_json(DATA_ROOT / "policies/phase3.v1.json")
    if set(policy["scenarios"]) != set(SCENARIOS) or not policy["version"]:
        raise ValueError("Business policy must name the five scenarios and its version.")
    taxonomy_ids = {entry["id"] for entry in reconciled["taxonomy"]}
    for scenario, rules in policy["scenarios"].items():
        if rules["taxonomy_id"] is not None and rules["taxonomy_id"] not in taxonomy_ids:
            raise ValueError("Business policy references an unknown taxonomy entry.")
        if not set(rules["required_documents"]) <= {
            d.key for d in load_fixture(scenario, "base").documents
        }:
            raise ValueError("Business policy references an unknown scenario document.")
    for client in clients:
        if not set(client.settings["disclosure_keys"]).issubset(keys):
            raise ValueError("Client references an unknown disclosure.")
    document_counts = Counter()
    fixture_count = 0
    for scenario in SCENARIOS:
        for variant in variants_for(scenario):
            fixture = load_fixture(scenario, variant)
            fixture_count += 1
            if fixture.client_code not in {client.code for client in clients}:
                raise ValueError("Scenario references an unknown client.")
            for document in fixture.documents:
                entry, content = library_document(scenario, variant, document.key)
                if entry["availability"] != document.availability:
                    raise ValueError("Document availability differs from its fixture.")
                document_counts[document.availability] += 1
                if document.availability == "available":
                    reader = PdfReader(BytesIO(content), strict=True)
                    text = "\n".join(page.extract_text() for page in reader.pages)
                    # Provenance may be printed or carried in the PDF keywords metadata.
                    text += "\n" + str((reader.metadata or {}).get("/Keywords", ""))
                    loan = document.declared_loan_identifier or fixture.loan_identifier
                    if not all(
                        value in text
                        for value in ("SYNTHETIC", loan, fixture.client_code, document.title)
                    ):
                        raise ValueError("Readable document does not match its declared identity.")
                elif document.availability == "missing" and content is not None:
                    raise ValueError("A missing attachment unexpectedly has file content.")
                elif document.availability == "unreadable":
                    try:
                        PdfReader(BytesIO(content), strict=True)
                    except Exception:
                        pass
                    else:
                        raise ValueError("The unreadable variant unexpectedly opens as a PDF.")
    return {
        "scenarios": len(SCENARIOS),
        "scenario_variants": fixture_count,
        "clients": len(clients),
        "taxonomy": 149,
        "source_rows": 527,
        "curated_items": len(knowledge),
        "documents": dict(document_counts),
        "raw_responses_exported": False,
        "business_policy": policy["version"],
    }
