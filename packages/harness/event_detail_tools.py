"""Read-only exact event detail tooling."""

import os
import re

from packages.api.evidence_service import EvidenceService
from packages.api.event_service import EventQueryService


EVENT_ID_PATTERN = re.compile(r"^evt_[0-9a-f]{32}$")


class EventDetailUnavailable(RuntimeError):
    """Raised when one exact event cannot be read safely."""


class EventDetailTools(object):
    def __init__(self, project_dir, database_path):
        self.event_service = EventQueryService(database_path)
        self.evidence_service = EvidenceService(
            os.path.abspath(project_dir)
        )

    def get_detail(self, arguments):
        event_id = str(arguments.get("event_id") or "").lower()
        if not EVENT_ID_PATTERN.match(event_id):
            raise EventDetailUnavailable(
                "event_id must be evt_ followed by 32 hex characters"
            )
        event = self.event_service.get_event(event_id)
        if event is None:
            raise EventDetailUnavailable("event does not exist")
        payload = self.evidence_service.add_urls(event)
        payload["read_only"] = True
        return payload
