import hashlib
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.assessment import assess_case
from app.main import create_app
from app.models import (
    ActionReceipt,
    CaseEvent,
    Concern,
    CorrespondenceCase,
    Evidence,
    FinalNote,
    IndexedPackage,
    Loan,
    OutboxEntry,
    ResponseDraft,
    ReviewDecision,
    RuleEvaluation,
    SpecialistTask,
)
from app.repository import fingerprint
from app.response_validation import validate_completion, validate_response
from app.routing import age, route_case
from app.rule_contracts import DraftCandidate, RoutingInputs, SpecialRoute
from app.simulators.artifacts import package_bytes


@pytest.mark.parametrize(
    "received,evaluated,days",
    [
        ("2026-09-04T10:00-04:00", "2026-09-04T12:00-04:00", 0),
        ("2026-09-04T10:00-04:00", "2026-09-06T12:00-04:00", 0),
        ("2026-09-04T10:00-04:00", "2026-09-07T12:00-04:00", 1),
        ("2026-09-05T10:00-04:00", "2026-09-07T12:00-04:00", 1),
        ("2026-09-01T10:00-04:00", "2026-09-28T12:00-04:00", 19),
        ("2026-09-01T10:00-04:00", "2026-09-29T12:00-04:00", 20),
        ("2026-09-01T10:00-04:00", "2026-09-30T12:00-04:00", 21),
        ("2026-10-30T10:00-04:00", "2026-11-02T12:00-05:00", 1),
        ("2026-09-21T02:00:00Z", "2026-09-21T14:00:00Z", 1),
        ("2026-11-01T05:30:00Z", "2026-11-01T06:30:00Z", 0),
        ("2026-03-06T12:00-05:00", "2026-03-09T12:00-04:00", 1),
    ],
)
def test_eastern_aging_examples(received, evaluated, days):
    result = route_case(received, evaluated, RoutingInputs(assessment="dispute"))
    assert result.aging.workdays == days
    assert result.route == ("Disputes" if days <= 20 else "Inquiry")
    assert result.aging.calendar_version == "eastern-mon-fri-v1"


@pytest.mark.parametrize(
    "received,evaluated",
    [
        (None, "2026-09-22T12:00Z"),
        ("bad", "2026-09-22T12:00Z"),
        ("2026-09-22T10:00", "2026-09-22T12:00Z"),
        ("2026-09-22T14:00Z", "2026-09-22T13:00Z"),
        ("2026-09-22T14:00Z", None),
    ],
)
def test_invalid_clock_blocks_only_ordinary_age_route(received, evaluated):
    assert age(received, evaluated).workdays is None
    ordinary = route_case(received, evaluated, RoutingInputs(assessment="dispute"))
    assert ordinary.route is None
    legal = route_case(
        received,
        evaluated,
        RoutingInputs(
            assessment="dispute",
            special_routes=[
                SpecialRoute(
                    route="Legal",
                    rule="RULE-08",
                    reason="Designated firm",
                    restrictions=["no_update"],
                )
            ],
        ),
    )
    assert legal.route == "Legal"
    assert legal.restrictions == ["no_update"]
    assert legal.findings[0].blocks == ["ordinary_route"]


def test_special_conflicts_precedence_and_assignment_are_independent():
    start, end = "2026-08-01T10:00Z", "2026-09-30T12:00Z"
    inputs = RoutingInputs(assessment="dispute", credit_error=True, queue="Inquiry")
    result = route_case(start, end, inputs)
    assert result.route == "Compliance" and result.aging.workdays > 20
    assert "manager_assignment" not in {f.code for f in result.findings}
    inputs.queue, inputs.email_owners = "Credit Reporting", ["One", "Two"]
    inputs.special_routes = [
        SpecialRoute(
            route="Legal", rule="RULE-08", reason="Legal warning", restrictions=["no_work"]
        )
    ]
    result = route_case(start, end, inputs)
    assert result.route == "Supervisory disposition"
    assert result.restrictions == ["no_work"]
    assert {f.code for f in result.findings} >= {
        "assignment_conflict",
        "manager_assignment",
        "special_route_conflict",
    }


@pytest.mark.parametrize("channel", ["chat", "call"])
def test_chat_call_assignment_requires_manager(channel):
    result = route_case(
        "2026-09-21T12:00Z",
        "2026-09-22T12:00Z",
        RoutingInputs(assessment="inquiry", channel=channel),
    )
    assert result.findings[0].code == "manager_assignment"


def load(client, scenario="DEMO-02", variant="base"):
    response = client.post(
        f"/api/scenarios/{scenario}/instances",
        json={"request_id": str(uuid4()), "variant": variant},
    )
    assert response.status_code == 201, response.text
    return response.json()


def report(client, case):
    response = client.get(f"/api/cases/{case['id']}/assessment")
    assert response.status_code == 200, response.text
    return response.json()


def codes(result):
    return {
        f["code"] if isinstance(f, dict) else f.code
        for f in (result["findings"] if isinstance(result, dict) else result.findings)
    }


def change_context(application, case, changes):
    with application.state.sessions() as session, session.begin():
        loan = session.get(Loan, case["loan_id"])
        loan.context = {**loan.context, **changes}
        for evidence in session.scalars(select(Evidence).where(Evidence.case_id == case["id"])):
            if evidence.details.get("kind") == "record":
                evidence.details = {**evidence.details, "facts": loan.context}


@pytest.mark.parametrize(
    "scenario,variant,status",
    [
        ("DEMO-01", "base", "waiting_for_borrower"),
        ("DEMO-01", "followup", "ready_for_response"),
        ("DEMO-02", "base", "ready_for_response"),
        ("DEMO-02", "missing_document", "waiting_on_department"),
        ("DEMO-02", "unreadable_document", "waiting_on_department"),
        ("DEMO-02", "wrong_loan", "waiting_on_department"),
        ("DEMO-03", "base", "ready_for_response"),
        ("DEMO-03", "followup", "ready_for_response"),
        ("DEMO-04", "base", "waiting_on_department"),
        ("DEMO-04", "followup", "specialist_handoff"),
        ("DEMO-05", "base", "waiting_for_borrower"),
        ("DEMO-05", "followup", "waiting_for_borrower"),
    ],
)
def test_selected_scenarios_have_explainable_dispositions(
    client, application, scenario, variant, status
):
    case = load(client, scenario, variant)
    assessment = report(client, case)
    assert assessment["disposition"] == status
    assert assessment["concerns"]
    if scenario == "DEMO-04":
        assert assessment["routing"]["route"] == "Compliance"
        assert "classification_mapping_missing" in codes(assessment)
        assert assessment["authorized_recipient"] == "counsel.demo@example.com"
    if scenario in {"DEMO-03", "DEMO-04"}:
        assert len(assessment["tasks"]) == 1
        assert assessment["tasks"][0]["action"] == "reuse"
        assert assessment["tasks"][0]["result_supported"] == (variant == "followup")
    if status.startswith("waiting"):
        assert all(
            c["owner"] and c["next_review_at"] and c["resume_requirement"]
            for c in assessment["concerns"]
        )
    with application.state.sessions() as session:
        assert session.get(CorrespondenceCase, case["id"]).status == "queued"
        assert session.scalar(select(func.count()).select_from(ActionReceipt)) == 0


def test_assessment_is_durable_idempotent_and_preserves_original_receipt(
    client, application, settings
):
    case = load(client)
    before = report(client, case)
    payload = {"request_id": str(uuid4()), "expected_revision": 1}
    first = client.post(f"/api/cases/{case['id']}/assessments", json=payload)
    assert first.status_code == 201, first.text
    assert client.post(f"/api/cases/{case['id']}/assessments", json=payload).json() == first.json()
    edited = client.patch(
        f"/api/cases/{case['id']}",
        json={"mutation_id": str(uuid4()), "expected_revision": 1, "owner": "New reviewer"},
    )
    assert edited.status_code == 200
    after = report(client, case)
    assert after["routing"]["aging"] == before["routing"]["aging"]
    assert after["input_hash"] != before["input_hash"]
    assert (
        client.post(
            f"/api/cases/{case['id']}/assessments", json={**payload, "request_id": str(uuid4())}
        ).status_code
        == 409
    )
    with TestClient(create_app(settings)) as restarted:
        history = restarted.get(f"/api/cases/{case['id']}/assessments").json()
        assert history == [first.json()]
    with application.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(RuleEvaluation)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(CaseEvent)
                .where(CaseEvent.kind == "rules.assessed")
            )
            == 1
        )


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({"requester_role": "executor"}, "requester_authority_missing"),
        ({"requester_role": "sii"}, "requester_authority_missing"),
        ({"requester_role": "co_borrower"}, "requester_authority_missing"),
        ({"requester_role": "attorney"}, "requester_authority_missing"),
        ({"csp_recipient": "wrong@example.com"}, "recipient_conflict"),
        ({"authorized_recipient": "wrong@example.com"}, "recipient_unverified"),
        ({"communication_restriction": "cease_and_desist"}, "cease_and_desist"),
        ({"product": "heloc"}, "product_policy_missing"),
    ],
)
def test_authority_and_product_exceptions(client, application, changes, expected):
    case = load(client)
    change_context(application, case, changes)
    assert expected in codes(report(client, case))


def test_unrelated_or_unsupported_task_cannot_supply_completion(client, application):
    case = load(client, "DEMO-03", "followup")
    with application.state.sessions() as session, session.begin():
        task = session.scalar(select(SpecialistTask).where(SpecialistTask.case_id == case["id"]))
        task.result = {"color": "green"}
    assert "task_result_unsupported" in codes(report(client, case))
    with application.state.sessions() as session, session.begin():
        task = session.scalar(select(SpecialistTask).where(SpecialistTask.case_id == case["id"]))
        task.request = {**task.request, "client_code": "OTHER"}
    assessment = report(client, case)
    assert "task_scope_conflict" in codes(assessment)
    assert assessment["tasks"][0]["action"] == "inspect_exception"


def candidate_for(client, case, response_type="final_resolution"):
    assessment = report(client, case)
    evidence = client.get(f"/api/cases/{case['id']}/evidence").json()
    record = next(e for e in evidence if e["details"]["kind"] == "record")
    context = record["details"]["facts"]
    client_config = context["client_configuration"]
    claims, attachments = [], []
    if case["family"] == "document_request" and response_type == "final_resolution":
        document = next(e for e in evidence if e["details"].get("key") == "amortization")
        attachments = [document["id"]]
        claims = [
            {
                "field": "document_attached",
                "value": document["title"],
                "evidence_id": document["id"],
            }
        ]
    if case["family"] == "tax_payment":
        claims = [
            {"field": f, "value": context[f], "evidence_id": record["id"]}
            for f in ("tax_bill_received_at", "tax_status", "tax_scheduled_date")
        ]
    return {
        "case_revision": case["revision"],
        "version": 1,
        "response_type": response_type,
        "client_code": case["client_code"],
        "client_version": client_config["version"],
        "sender": client_config["sender_email"],
        "recipient": context["authorized_recipient"],
        "evidence_versions": assessment["evidence_versions"],
        "attachment_ids": attachments,
        "disclosure_ids": client_config["disclosure_keys"],
        "concerns": [
            {"concern_id": c["concern_id"], "disposition": c["disposition"]}
            for c in assessment["concerns"]
        ],
        "claims": claims,
    }


def validate(client, case, candidate):
    response = client.post(f"/api/cases/{case['id']}/validate-response", json=candidate)
    assert response.status_code == 200, response.text
    return response.json()


def test_supported_response_and_pending_request(client):
    case = load(client)
    candidate = candidate_for(client, case)
    result = validate(client, case, candidate)
    assert result["valid"], result
    assert validate(client, case, {**candidate, "body": result["rendered_body"]})["valid"]
    interim_case = load(client, "DEMO-01")
    interim = candidate_for(client, interim_case, "information_request")
    result = validate(client, interim_case, interim)
    assert result["valid"] and result["resulting_status"] == "waiting_for_borrower"
    assert "unresolved_concerns" in codes(
        validate(client, interim_case, {**interim, "response_type": "final_resolution"})
    )


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("case_revision", 999, "stale_case_revision"),
        ("evidence_versions", {}, "stale_evidence"),
        ("attachment_ids", [], "required_attachment_missing"),
        ("concerns", [], "concern_coverage"),
        ("client_code", "DEMO-HARBOR", "wrong_client"),
        ("sender", "wrong@example.com", "wrong_sender"),
        ("recipient", "wrong@example.com", "wrong_recipient"),
        ("disclosure_ids", [], "disclosure_mismatch"),
        (
            "body",
            "Your tax bill has been paid and the bankruptcy was discharged.",
            "unchecked_response_text",
        ),
    ],
)
def test_response_rejects_stale_or_unsafe_candidates(client, field, value, expected):
    case = load(client)
    candidate = candidate_for(client, case)
    candidate[field] = value
    result = validate(client, case, candidate)
    assert not result["valid"] and expected in codes(result)


@pytest.mark.parametrize(
    "field,value",
    [
        ("tax_status", "paid"),
        ("tax_amount_minor", 1),
        ("tax_due_date", "2026-10-29"),
        ("loan_identifier", "0099000099"),
        ("tax_paid_at", "2026-10-27T12:00Z"),
    ],
)
def test_citations_do_not_prove_false_facts(client, field, value):
    case = load(client, "DEMO-03")
    candidate = candidate_for(client, case)
    candidate["claims"].append(
        {"field": field, "value": value, "evidence_id": candidate["claims"][0]["evidence_id"]}
    )
    result = validate(client, case, candidate)
    assert not result["valid"] and "unsupported_claim" in codes(result)
    if field == "tax_status":
        assert "contradictory_claims" in codes(result)


def test_bankruptcy_definitive_claim_requires_consistent_specialist_result(client):
    case = load(client, "DEMO-04")
    candidate = candidate_for(client, case, "interim_acknowledgment")
    evidence = client.get(f"/api/cases/{case['id']}/evidence").json()
    record = next(e for e in evidence if e["details"]["kind"] == "record")
    candidate["claims"] = [
        {"field": "bankruptcy_status", "value": "discharged", "evidence_id": record["id"]}
    ]
    assert "unsupported_claim" in codes(validate(client, case, candidate))
    followup = load(client, "DEMO-04", "followup")
    candidate = candidate_for(client, followup, "referral")
    evidence = client.get(f"/api/cases/{followup['id']}/evidence").json()
    determination = next(
        e for e in evidence if e["details"].get("key") == "specialist-determination"
    )
    candidate["claims"] = [
        {
            "field": "bankruptcy_status",
            "value": "dismissed_without_discharge",
            "evidence_id": determination["id"],
        }
    ]
    assert validate(client, followup, candidate)["valid"]


def test_bad_files_and_cross_case_citations_are_rejected(client, application, settings):
    for variant in ["missing_document", "unreadable_document", "wrong_loan"]:
        case = load(client, variant=variant)
        assert "invalid_attachment" in codes(validate(client, case, candidate_for(client, case)))
    case, other = load(client), load(client)
    candidate = candidate_for(client, case)
    candidate["claims"][0]["evidence_id"] = candidate_for(client, other)["claims"][0]["evidence_id"]
    assert "unsupported_claim" in codes(validate(client, case, candidate))
    candidate = candidate_for(client, case)
    with application.state.sessions() as session:
        row = session.get(Evidence, candidate["attachment_ids"][0])
        (settings.data_dir / "documents" / row.storage_key).write_bytes(b"changed")
    assert "invalid_attachment" in codes(validate(client, case, candidate))


def test_complete_requires_actual_matching_records_and_fresh_approval(
    client, application, settings
):
    case = load(client, "DEMO-03")
    candidate = DraftCandidate.model_validate(candidate_for(client, case))
    with application.state.sessions() as session, session.begin():
        for concern in session.scalars(select(Concern).where(Concern.case_id == case["id"])):
            concern.disposition = "resolved"
        session.flush()
        assessment, _ = assess_case(session, settings.data_dir, case["id"])
        result = validate_response(session, settings.data_dir, case["id"], candidate)
        assert result.valid
        stored_candidate = candidate.model_dump(mode="json")
        draft = ResponseDraft(
            case_id=case["id"],
            version=1,
            case_revision=case["revision"],
            response_type="final_resolution",
            body=result.rendered_body,
            recipient=candidate.recipient,
            evidence_versions=candidate.evidence_versions,
            attachment_ids=candidate.attachment_ids,
            disclosure_ids=candidate.disclosure_ids,
            validation={"candidate": stored_candidate, "input_hash": assessment.input_hash},
        )
        session.add(draft)
        session.flush()
        content_hash = fingerprint(
            {"candidate": stored_candidate, "input_hash": assessment.input_hash}
        )
        review = ReviewDecision(
            case_id=case["id"],
            draft_id=draft.id,
            draft_version=1,
            case_revision=case["revision"],
            actor="reviewer",
            decision="approve",
            note="",
            content_hash=content_hash,
        )
        session.add(review)
        actions = []
        for operation in ("csp.send", "onbase.index", "ils.final_note"):
            action = ActionReceipt(
                case_id=case["id"],
                operation=operation,
                idempotency_key=str(uuid4()),
                payload_hash="test",
                status="simulated_complete",
                payload={
                    "draft_id": draft.id,
                    "draft_version": draft.version,
                    "loan_identifier": case["loan_identifier"],
                },
                result={"reference": str(uuid4())},
            )
            session.add(action)
            session.flush()
            actions.append(action)
        assert "delivery_missing" in codes(
            validate_completion(session, settings.data_dir, case["id"])
        )
        outbox = OutboxEntry(
            action_id=actions[0].id,
            draft_id=draft.id,
            status="sent",
            delivery_reference="demo-send",
            sent_content={
                "draft_id": draft.id,
                "draft_version": 1,
                "case_revision": 1,
                "body": draft.body,
                "recipient": draft.recipient,
                "attachment_ids": [],
                "attachments": [],
                "schema_version": 4,
                "client_code": case["client_code"],
                "loan_identifier": case["loan_identifier"],
                "ccid": case["ccid"],
                "simulation_id": case["simulation_id"],
                "sender": candidate.sender,
                "evidence_versions": candidate.evidence_versions,
            },
        )
        session.add(outbox)
        session.flush()
        assert (
            validate_completion(session, settings.data_dir, case["id"]).resulting_status
            == "records_incomplete"
        )
        pdf, page_count = package_bytes(
            session.get(CorrespondenceCase, case["id"]),
            session.get(Loan, case["loan_id"]),
            outbox.sent_content,
            [],
        )
        pdf_path = settings.data_dir / "documents" / "indexed-test.pdf"
        pdf_path.write_bytes(pdf)
        fields = {
            "draft_id": draft.id,
            "draft_version": 1,
            "outbox_id": outbox.id,
            "sherman_id": case["loan_identifier"],
            "ccid": case["ccid"],
            "case_id": case["id"],
            "client_code": case["client_code"],
            "simulation_id": case["simulation_id"],
            "document_type": "Borrower Correspondence (Demo)",
            "correspondence_type": "INQ Email Reply",
            "body_sha256": hashlib.sha256(draft.body.encode()).hexdigest(),
            "pdf_storage_key": pdf_path.name,
            "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
            "page_count": page_count,
        }
        content = json.dumps({"sent_content": outbox.sent_content, "index_fields": fields}).encode()
        path = settings.data_dir / "documents" / "indexed-test.json"
        path.write_bytes(content)
        package = IndexedPackage(
            case_id=case["id"],
            action_id=actions[1].id,
            storage_key=path.name,
            content_sha256=hashlib.sha256(content).hexdigest(),
            index_fields=fields,
        )
        note = FinalNote(
            case_id=case["id"],
            action_id=actions[2].id,
            department="Servicing",
            note_type="INQ Email Reply",
            details={
                "standout_comment": True,
                "recipient": candidate.recipient,
                "outbox_id": outbox.id,
                "draft_version": 1,
            },
            content="All concerns answered; scheduled payment remains unpaid.",
        )
        session.add_all([package, note])
        session.flush()
        completed = validate_completion(session, settings.data_dir, case["id"])
        assert completed.valid, completed.model_dump()
        review.content_hash = "old"
        session.flush()
        assert "approval_missing_or_stale" in codes(
            validate_completion(session, settings.data_dir, case["id"])
        )
        review.content_hash = content_hash
        actions[1].status = "failed"
        session.flush()
        assert "index_missing" in codes(validate_completion(session, settings.data_dir, case["id"]))
        actions[1].status = "simulated_complete"
        draft.body += " A new unchecked claim."
        session.flush()
        assert "stale_draft" in codes(validate_completion(session, settings.data_dir, case["id"]))


def test_empty_completion_never_closes(client):
    case = load(client)
    result = client.get(f"/api/cases/{case['id']}/completion-check").json()
    assert not result["valid"]
    assert codes(result) >= {
        "response_not_prepared",
        "delivery_missing",
        "index_missing",
        "final_note_missing",
        "concerns_incomplete",
    }


def test_new_concern_and_conflicting_tax_facts_cannot_be_hidden(client, application):
    case = load(client, "DEMO-03")
    with application.state.sessions() as session, session.begin():
        session.add(
            Concern(
                case_id=case["id"], description="Please also investigate a refund.", evidence_ids=[]
            )
        )
    assessment = report(client, case)
    assert "additional_concern_unassessed" in codes(assessment)
    assert assessment["disposition"] == "waiting_on_department"
    candidate = candidate_for(client, case)
    assert "unresolved_concerns" in codes(validate(client, case, candidate))
    change_context(application, case, {"tax_amount_minor": 999})
    assert "tax_evidence_conflict" in codes(report(client, case))


def test_existing_task_absence_does_not_authorize_creation(client, application):
    case = load(client, "DEMO-04")
    with application.state.sessions() as session, session.begin():
        task = session.scalar(select(SpecialistTask).where(SpecialistTask.case_id == case["id"]))
        session.delete(task)
    assessment = report(client, case)
    assert not assessment["tasks"]
    assert assessment["disposition"] == "waiting_on_department"
    assert not any("create" in action.lower() for action in assessment["permitted_actions"])
    with application.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(SpecialistTask)) == 0


def test_verified_role_and_representation_do_not_imply_cease_and_desist(client, application):
    case = load(client, "DEMO-04")
    assert "cease_and_desist" not in codes(report(client, case))
    change_context(application, case, {"requester_role": "attorney"})
    with application.state.sessions() as session, session.begin():
        authorization = next(
            e
            for e in session.scalars(select(Evidence).where(Evidence.case_id == case["id"]))
            if e.details.get("key") == "representation"
        )
        authorization.details = {
            **authorization.details,
            "facts": {**authorization.details["facts"], "authorized_role": "attorney"},
        }
    assert "requester_authority_missing" not in codes(report(client, case))


def test_name_update_requires_valid_date_identity_and_result(client, application):
    case = load(client, "DEMO-01", "followup")
    with application.state.sessions() as session, session.begin():
        signed = next(
            e
            for e in session.scalars(select(Evidence).where(Evidence.case_id == case["id"]))
            if e.details.get("key") == "signed-request"
        )
        signed.details = {
            **signed.details,
            "facts": {**signed.details["facts"], "signed_date": "not-a-date"},
        }
    assert "name_change_evidence_missing" in codes(report(client, case))


def test_supported_name_update_claim_and_pending_task_claim(client):
    case = load(client, "DEMO-01", "followup")
    candidate = candidate_for(client, case)
    record = next(
        e
        for e in client.get(f"/api/cases/{case['id']}/evidence").json()
        if e["details"]["kind"] == "record"
    )
    task = client.get(f"/api/cases/{case['id']}/tasks").json()[0]
    candidate["claims"] = [
        {
            "field": "current_legal_name",
            "value": "Lauren E. Castellano",
            "evidence_id": record["id"],
        },
        {
            "field": "task_completed",
            "value": task["result"]["reference"],
            "evidence_id": task["id"],
        },
    ]
    assert validate(client, case, candidate)["valid"]
    tax_case = load(client, "DEMO-03")
    candidate = candidate_for(client, tax_case)
    task = client.get(f"/api/cases/{tax_case['id']}/tasks").json()[0]
    candidate["claims"].append(
        {"field": "task_completed", "value": "invented-completion", "evidence_id": task["id"]}
    )
    assert "unsupported_claim" in codes(validate(client, tax_case, candidate))
