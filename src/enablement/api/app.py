"""Local HTTP lab. Bearer tokens are fixtures."""

from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from enablement import __version__
from enablement.auth import Actor, actor_from_token
from enablement.errors import LabError
from enablement.gates import DEPLOYMENT_DECISION, GATES
from enablement.session import Session
from enablement.store import Store
from enablement.workflow import decide, investigate, public_view, resume

_STATUS = {
    "not_found": 404,
    "unauthorized": 403,
    "denied": 403,
    "expired": 409,
    "invalid": 400,
}


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grant_id: str


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]


def create_app() -> FastAPI:
    app = FastAPI(title="IdentityGuard Claude enablement", version=__version__)
    app.state.store = Store()
    app.state.sessions = {}

    @app.exception_handler(LabError)
    def _on_lab_error(_request, exc: LabError):
        return JSONResponse(
            status_code=_STATUS.get(exc.code, 400),
            content={"error": exc.code, "detail": exc.message},
        )

    def require_actor(authorization: str | None = Header(default=None)) -> Actor:
        if authorization is None or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="authentication required")
        token = authorization.split(" ", 1)[1].strip()
        try:
            return actor_from_token(token)
        except LabError:
            raise HTTPException(status_code=401, detail="authentication required") from None

    def owned(session_id: str, actor: Actor) -> Session:
        session = app.state.sessions.get(session_id)
        if session is None or session.tenant_id != actor.tenant_id:
            raise LabError("not_found", "review not found")
        return session

    @app.get("/healthz")
    def healthz():
        return {
            "status": "ok",
            "package": "identityguard-claude-enablement",
            "version": __version__,
            "mode": "local-mock",
            "remote_called": False,
            "real_customer_data": 0,
            "deployment_decision": DEPLOYMENT_DECISION,
            "gates": GATES,
        }

    @app.post("/v1/reviews")
    def open_review(body: ReviewIn, actor: Actor = Depends(require_actor)):
        session, report = investigate(app.state.store, actor, body.grant_id)
        app.state.sessions[session.session_id] = session
        return public_view(session, report)

    @app.get("/v1/reviews/{session_id}")
    def get_review(session_id: str, actor: Actor = Depends(require_actor)):
        return public_view(owned(session_id, actor))

    @app.post("/v1/approvals/{approval_id}/decision")
    def post_decision(approval_id: str, body: DecisionIn, actor: Actor = Depends(require_actor)):
        return decide(app.state.store, actor, approval_id, body.decision)

    @app.post("/v1/reviews/{session_id}/resume")
    def post_resume(session_id: str, actor: Actor = Depends(require_actor)):
        session = owned(session_id, actor)
        if session.subject != actor.subject:
            raise LabError("unauthorized", "only the requesting engineer can resume")
        session, report = resume(app.state.store, session)
        return public_view(session, report)

    @app.get("/v1/audit/{session_id}")
    def get_audit(session_id: str, actor: Actor = Depends(require_actor)):
        session = owned(session_id, actor)
        return {"session_id": session.session_id, "audit": session.audit}

    return app
