"""Browser-test server only. Never imported by the production application."""

import sys
from pathlib import Path

from fastapi import Request

sys.path.insert(0, str(Path(__file__).parent))

from test_custom_mail import IntakeModel  # noqa: E402
from test_phase6 import choice  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import ClientConfiguration  # noqa: E402


class BrowserModel(IntakeModel):
    def choose(self, observation, history, timeout):
        if observation:
            if not observation["plan_current"]:
                return choice("apply_plan")
            saved = observation["saved"]
            current = [d for d in saved["drafts"] if d["current"] and not d["returned"]]
            observation = {**observation, "saved": {**saved, "drafts": current}}
        return super().choose(observation, history, timeout)


app = create_app(Settings(), agent_model=BrowserModel())


@app.post("/test-only/require-review")
def require_review(request: Request):
    with request.app.state.sessions() as session, session.begin():
        client = session.get(ClientConfiguration, "DEMO-NORTH")
        client.settings = {**client.settings, "default_review_mode": "review_required"}
    return {"configured": True}
