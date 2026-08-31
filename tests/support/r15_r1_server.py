"""Host the real web app with deterministic collaborators for Playwright."""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from .r15_r1_app import create_test_root, make_application
from pd_agent.web import create_app
from pd_agent.web.security import LocalWebSecurityPolicy


def main() -> None:
    root = Path(os.environ.get("PD_AGENT_R15_R1_ROOT", "")) if os.environ.get("PD_AGENT_R15_R1_ROOT") else create_test_root()
    root.mkdir(parents=True, exist_ok=True)
    application, workspace, provider, _ = make_application(root)
    os.environ["PD_AGENT_E2E_WORKSPACE"] = str(workspace)
    os.environ["PD_AGENT_R15_R1_ROOT"] = str(root)
    port = int(os.environ.get("PD_AGENT_R15_R1_PORT", "8765"))
    app = create_app(
        services=application.web_services,
        frontend_dist=Path(__file__).resolve().parents[2] / "frontend" / "dist",
        policy=LocalWebSecurityPolicy(allowed_origins=(f"http://127.0.0.1:{port}", f"http://localhost:{port}")),
    )
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
