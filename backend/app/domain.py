from enum import StrEnum


class CaseFamily(StrEnum):
    PROFILE_CHANGE = "profile_change"
    DOCUMENT_REQUEST = "document_request"
    TAX_PAYMENT = "tax_payment"
    CREDIT_REPORTING = "credit_reporting"
    LOAN_SERVICING = "loan_servicing"


class CaseStatus(StrEnum):
    QUEUED = "queued"
    ASSIGNMENT_EXCEPTION = "assignment_exception"
    UNDER_REVIEW = "under_review"
    WAITING_FOR_BORROWER = "waiting_for_borrower"
    WAITING_ON_DEPARTMENT = "waiting_on_department"
    READY_FOR_RESPONSE = "ready_for_response"
    AWAITING_REVIEW = "awaiting_review"
    RECORDS_INCOMPLETE = "records_incomplete"
    CLOSED = "closed"
    TRANSFERRED = "transferred"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_INPUT = "waiting_for_input"
    WAITING_FOR_REVIEW = "waiting_for_review"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class ActionStatus(StrEnum):
    REJECTED = "rejected"
    PREPARED = "prepared"
    AWAITING_REVIEW = "awaiting_review"
    IN_PROGRESS = "in_progress"
    SIMULATED_COMPLETE = "simulated_complete"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


class DomainError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message
        super().__init__(message)
