"""Sub-agent sessions copy tenant context and keep a narrower allow list."""

from enablement.agent import run_turns
from enablement.session import Session, child_session
from enablement.store import Store


def delegate(store: Store, parent: Session, task: str, script: list[dict]) -> tuple[Session, dict]:
    child = child_session(store, parent, task)
    report = run_turns(child, store, script, task)
    child.completion_claimed = False
    child.status = "STOPPED"
    store.remember_session(child.snapshot())
    return child, report
