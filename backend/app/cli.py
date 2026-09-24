import argparse
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from app.config import Settings
from app.db import make_engine, make_sessions
from app.migrations import upgrade_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Correspondence foundation utilities")
    parser.add_argument(
        "command",
        choices=[
            "migrate",
            "export-openapi",
            "check-openapi",
            "serve",
            "rebuild-data",
            "check-data",
            "seed-demo",
        ],
    )
    parser.add_argument(
        "--scenario",
        default="all",
        choices=["all", "DEMO-01", "DEMO-02", "DEMO-03", "DEMO-04", "DEMO-05"],
    )
    parser.add_argument(
        "--variant",
        default="base",
        choices=["base", "missing_document", "unreadable_document", "wrong_loan", "followup"],
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Create new instances without altering previous history.",
    )
    args = parser.parse_args()
    settings = Settings()
    if args.command == "rebuild-data":
        from app.documents import build_documents
        from app.source_catalog import export_catalogs

        report = export_catalogs()
        documents = build_documents()
        print(
            f"Reconciled {report['taxonomy_count']} taxonomy combinations and {report['knowledge_row_count']} source rows; {len(documents)} document entries. No raw responses exported."
        )
    elif args.command == "check-data":
        from app.data_validation import validate_data

        print(json.dumps(validate_data(), indent=2))
    elif args.command in {"export-openapi", "check-openapi"}:
        from app.main import create_app

        snapshot = Path(__file__).resolve().parents[1] / "openapi.json"
        encoded = json.dumps(create_app(settings).openapi(), indent=2, ensure_ascii=False) + "\n"
        if args.command == "export-openapi":
            snapshot.write_text(encoded, encoding="utf-8")
            print("Exported backend/openapi.json (no environment values).")
        elif not snapshot.exists() or snapshot.read_text(encoding="utf-8") != encoded:
            raise SystemExit("OpenAPI snapshot is stale. Export it and regenerate frontend types.")
        else:
            print("OpenAPI snapshot matches the application contract.")
    elif args.command == "serve":
        import uvicorn

        uvicorn.run("app.main:app", host=settings.app_host, port=settings.app_port)
    else:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        engine = make_engine(settings.database_url)
        try:
            upgrade_database(engine)
            from app.catalogs import install_catalogs

            sessions = make_sessions(engine)
            with sessions() as session, session.begin():
                install_catalogs(session)
            if args.command == "seed-demo":
                from app.fixture_data import SCENARIOS
                from app.seeding import seed_scenario

                if args.scenario == "all" and args.variant != "base":
                    raise SystemExit("Choose an individual scenario when loading a variant.")
                keys = SCENARIOS if args.scenario == "all" else [args.scenario]
                for key in keys:
                    request_id = (
                        uuid4()
                        if args.fresh
                        else uuid5(NAMESPACE_URL, f"correspondence/seed/v1/{key}/{args.variant}")
                    )
                    with sessions() as session:
                        result = seed_scenario(session, settings, key, args.variant, request_id)
                        print(
                            f"{key} ({args.variant}) case={result.id} simulation={result.simulation_id}"
                        )
            else:
                print("Database migrations and reference catalogs are current.")
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
