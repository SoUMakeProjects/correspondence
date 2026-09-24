from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.fixture_contracts import ClientFixture, KnowledgeFixture
from app.models import ClientConfiguration, KnowledgeItem, SourceManifestEntry, TaxonomyEntry
from app.source_catalog import DATA_ROOT, read_json


def install_catalogs(session: Session) -> dict:
    """Add versioned reference records, preserving existing runtime decisions/history."""
    definitions = [
        (TaxonomyEntry, read_json(DATA_ROOT / "knowledge/taxonomy.v1.json")),
        (SourceManifestEntry, read_json(DATA_ROOT / "knowledge/source_manifest.v1.json")),
    ]
    for model, rows in definitions:
        existing = set(session.scalars(select(model.id)))
        session.add_all(model(**row) for row in rows if row["id"] not in existing)
    existing_clients = {c.code: c for c in session.scalars(select(ClientConfiguration))}
    for row in read_json(DATA_ROOT / "fixtures/v1/clients.json"):
        client = ClientFixture.model_validate(row)
        stored = existing_clients.get(client.code)
        if stored is None:
            session.add(ClientConfiguration(**client.model_dump()))
        elif stored.version < client.version:
            # A newer published client version supersedes the stored one. Existing cases keep
            # their own snapshot and are reported as needing a configuration refresh.
            stored.version = client.version
            stored.display_name = client.display_name
            stored.settings = client.settings
    existing_knowledge = set(session.scalars(select(KnowledgeItem.id)))
    for row in read_json(DATA_ROOT / "knowledge/curated.v1.json"):
        item = KnowledgeFixture.model_validate(row)
        identity = str(uuid5(NAMESPACE_URL, f"correspondence/knowledge/{item.key}/v{item.version}"))
        if identity not in existing_knowledge:
            session.add(
                KnowledgeItem(
                    id=identity,
                    version=item.version,
                    status=item.status,
                    source_reference=";".join(item.source_references),
                    content=item.content,
                    applicability=item.model_dump(
                        mode="json", exclude={"version", "status", "content"}
                    ),
                )
            )
    session.flush()
    return read_json(DATA_ROOT / "knowledge/reconciliation.v1.json")


def search_knowledge(
    session: Session, scenario_id: str, client_code: str, query: str = "", kind: str | None = None
) -> list[dict]:
    # Both provenance review state and applicability are checked; source-manifest
    # rows (including unresolved fragments) are never searched as response content.
    tokens = query.casefold().split()
    result = []
    for item in session.scalars(
        select(KnowledgeItem).where(KnowledgeItem.status == "curated_demo")
    ):
        record = KnowledgeFixture.model_validate(
            {
                **item.applicability,
                "version": item.version,
                "status": item.status,
                "content": item.content,
            }
        )
        if scenario_id not in record.scenario_ids or client_code not in record.client_codes:
            continue
        if kind and record.kind != kind:
            continue
        haystack = f"{record.title} {record.content}".casefold()
        if not all(token in haystack for token in tokens):
            continue
        result.append({"id": item.id, **record.model_dump(mode="json")})
    return sorted(result, key=lambda row: row["key"])
