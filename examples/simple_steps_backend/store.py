"""In-memory workflow store.

A workflow is persisted as a single session snapshot (structure + payloads).
Swap this for a database table in production; keep the same interface.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WorkflowRecord:
    workflow_id: str
    snapshot_json: str        # Workflow.export_session_json()
    status: str = "created"   # created | running | completed | failed


class WorkflowStore:
    def __init__(self) -> None:
        self._records: dict[str, WorkflowRecord] = {}

    def save(self, record: WorkflowRecord) -> None:
        self._records[record.workflow_id] = record

    def load(self, workflow_id: str) -> WorkflowRecord | None:
        return self._records.get(workflow_id)

    def set_status(self, workflow_id: str, status: str) -> None:
        if workflow_id in self._records:
            self._records[workflow_id].status = status

    def update_snapshot(self, workflow_id: str, snapshot_json: str) -> None:
        if workflow_id in self._records:
            self._records[workflow_id].snapshot_json = snapshot_json

    def list_ids(self) -> list[str]:
        return list(self._records)
