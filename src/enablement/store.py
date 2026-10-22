"""Process-local grant and approval state."""

import threading
import time
from copy import deepcopy

from enablement.catalog import GRANTS, POLICIES, PUBLIC_GRANT_FIELDS
from enablement.errors import LabError


class Store:
    def __init__(self, clock=None) -> None:
        self.clock = clock or time.time
        self._lock = threading.Lock()
        self.grants = deepcopy(GRANTS)
        self.policies = deepcopy(POLICIES)
        self.approvals: dict[str, dict] = {}
        self.sessions: dict[str, dict] = {}
        self._session_seq = 0
        self._approval_seq = 0

    def next_session_id(self) -> str:
        with self._lock:
            self._session_seq += 1
            return f"SYN-SESSION-{self._session_seq:03d}"

    def remember_session(self, record: dict) -> None:
        with self._lock:
            self.sessions[record["session_id"]] = record

    def session(self, session_id: str) -> dict | None:
        with self._lock:
            row = self.sessions.get(session_id)
            return deepcopy(row) if row else None

    def grant_for(self, grant_id: str, tenant_id: str) -> dict | None:
        with self._lock:
            row = self.grants.get(grant_id)
            if row is None or row["tenant_id"] != tenant_id:
                return None
            return {key: row[key] for key in PUBLIC_GRANT_FIELDS}

    def policy_for(self, policy_id: str, tenant_id: str) -> dict | None:
        with self._lock:
            row = self.policies.get(policy_id)
            if row is None or row["tenant_id"] != tenant_id:
                return None
            return deepcopy(row)

    def create_approval(self, grant_id: str, tenant_id: str, requester: str, session_id: str) -> dict:
        with self._lock:
            grant = self.grants.get(grant_id)
            if grant is None or grant["tenant_id"] != tenant_id:
                raise LabError("not_found", "grant not found")
            for existing in self.approvals.values():
                if existing["grant_id"] == grant_id and existing["status"] == "pending":
                    return deepcopy(existing)
            self._approval_seq += 1
            approval_id = f"SYN-APR-{self._approval_seq:03d}"
            record = {
                "approval_id": approval_id,
                "grant_id": grant_id,
                "tenant_id": tenant_id,
                "requester_subject": requester,
                "requester_session_id": session_id,
                "status": "pending",
                "approver_subject": "",
                "expires_at": self.clock() + 3600,
            }
            self.approvals[approval_id] = record
            return deepcopy(record)

    def approval(self, approval_id: str) -> dict | None:
        with self._lock:
            row = self.approvals.get(approval_id)
            return deepcopy(row) if row else None

    def expire(self, approval_id: str) -> None:
        with self._lock:
            row = self.approvals.get(approval_id)
            if row is None:
                raise LabError("not_found", "approval not found")
            row["expires_at"] = self.clock() - 1

    def decide(self, approval_id: str, tenant_id: str, subject: str, role: str, decision: str) -> dict:
        if decision not in {"approve", "reject"}:
            raise LabError("invalid", "decision must be approve or reject")
        if role != "approver":
            raise LabError("unauthorized", "approver role required")
        with self._lock:
            row = self.approvals.get(approval_id)
            if row is None or row["tenant_id"] != tenant_id:
                raise LabError("not_found", "approval not found")
            if subject == row["requester_subject"]:
                raise LabError("denied", "requester cannot approve")
            if self.clock() >= row["expires_at"]:
                raise LabError("expired", "approval expired")
            if row["status"] != "pending":
                raise LabError("denied", "approval is already decided")
            row["status"] = "approved" if decision == "approve" else "rejected"
            row["approver_subject"] = subject
            return deepcopy(row)

    def record(self, approval_id: str, tenant_id: str, subject: str, role: str, grant_id: str) -> dict:
        with self._lock:
            reason = self._record_block_unlocked(approval_id, tenant_id, subject, role, grant_id)
            if reason is not None:
                code, message = reason
                raise LabError(code, message)
            approval = self.approvals[approval_id]
            grant = self.grants[grant_id]
            grant["status"] = "recorded"
            return {
                "recorded": True,
                "grant_id": grant_id,
                "approval_id": approval_id,
                "status": "recorded",
                "live_directory": False,
                "remote_called": False,
                "approver_subject": approval["approver_subject"],
            }

    def record_allowed(self, approval_id: str, tenant_id: str, subject: str, role: str, grant_id: str) -> bool:
        with self._lock:
            return self._record_block_unlocked(approval_id, tenant_id, subject, role, grant_id) is None

    def _record_block_unlocked(self, approval_id, tenant_id, subject, role, grant_id):
        if role != "engineer":
            return "unauthorized", "engineer role required"
        approval = self.approvals.get(approval_id)
        if approval is None or approval["tenant_id"] != tenant_id:
            return "not_found", "approval not found"
        if approval["grant_id"] != grant_id:
            return "denied", "approval does not match the grant"
        if self.clock() >= approval["expires_at"]:
            return "expired", "approval expired"
        if approval["status"] == "rejected":
            return "denied", "approval was rejected"
        if approval["status"] != "approved":
            return "denied", "approval is pending"
        if subject == approval["approver_subject"]:
            return "denied", "approver cannot record the write"
        grant = self.grants.get(grant_id)
        if grant is None or grant["tenant_id"] != tenant_id:
            return "not_found", "grant not found"
        return None
