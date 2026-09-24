"""Test-only subprocess app: real worker/simulators with an explicitly labeled test model.

Not imported by the application. The optional hard exit exercises a committed send before
its worker checkpoint. It is enabled only by this test server command and marker path.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_phase6 import TestModel  # noqa: E402

import app.agent_tools as tool_module  # noqa: E402
from app.agent import AgentWorker  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

original_init = AgentWorker.__init__


def quick_lease(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    self.lease_seconds = 2  # Deterministic calls only; normal/live leases remain unchanged.


AgentWorker.__init__ = quick_lease
original_dispatch = tool_module.dispatch


def crash_after_send(*args, **kwargs):
    result = original_dispatch(*args, **kwargs)
    marker = os.environ.get("TEST_CRASH_MARKER")
    if marker and args[4].command.operation == "csp.send" and result.status == "simulated_complete":
        Path(marker).write_text(
            "Committed send; worker checkpoint intentionally interrupted.", encoding="utf-8"
        )
        os._exit(86)
    return result


tool_module.dispatch = crash_after_send
app = create_app(Settings(), agent_model=TestModel())
