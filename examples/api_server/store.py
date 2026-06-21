"""In-memory workflow store for the example API server.

Persists each workflow as a full-session snapshot (structure + payloads) keyed
by ``workflow_id``. A real backend would swap this for a database/object store;
the surface (``save`` / ``load``) is deliberately tiny so it is easy to replace.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WorkflowRecord:
    workflow_id: str
    user_id: str
    snapshot_json: str          # SessionSnapshot JSON (structure + payloads)
    status: str = "created"     # created | running | completed | failed


@dataclass
class WorkflowStore:
    _records: dict[str, WorkflowRecord] = field(default_factory=dict)

    def save(self, record: WorkflowRecord) -> None:
        self._records[record.workflow_id] = record

    def load(self, workflow_id: str) -> WorkflowRecord | None:
        return self._records.get(workflow_id)

    def set_status(self, workflow_id: str, status: str) -> None:
        record = self._records.get(workflow_id)
        if record is not None:
            record.status = status

    def update_snapshot(self, workflow_id: str, snapshot_json: str) -> None:
        record = self._records.get(workflow_id)
        if record is not None:
            record.snapshot_json = snapshot_json


STORE = WorkflowStore()
