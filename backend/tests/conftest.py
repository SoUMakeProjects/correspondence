from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import WORKSPACE_ROOT, Settings
from app.main import create_app


def pytest_configure(config):
    # Use a fresh workspace-local directory; old system-temp ACLs may belong to
    # a different Windows sandbox identity after an interrupted session.
    if config.option.basetemp is None:
        destination = WORKSPACE_ROOT / ".local" / "pytest" / str(uuid4())
        destination.parent.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = str(destination)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        azure_openai_base_url="",
        azure_openai_deployment="",
        azure_openai_api_key="",
        azure_openai_live_tests_enabled=False,
    )


@pytest.fixture
def application(settings):
    return create_app(settings, start_worker=False)


@pytest.fixture
def client(application):
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture
def case_payload():
    return {
        "request_id": str(uuid4()),
        "loan_identifier": "000000012345",
        "ccid": "00009876",
        "client_code": "DEMO-NORTH",
        "borrower_display_name": "Jordan Sample",
        "balance_minor": 123456789,
        "currency": "USD",
        "subject": "Synthetic document request",
        "correspondence_text": "Please provide my amortization schedule.",
        "family": "document_request",
        "owner": "Demo reviewer",
        "original_received_at": "2026-11-01T01:30:00.123456-04:00",
    }
