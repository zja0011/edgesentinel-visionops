"""Safe resolution of event evidence files for HTTP responses."""

import os
from urllib.parse import quote


class EvidenceNotFound(LookupError):
    """Raised when an event has no safe evidence file of the requested kind."""


class EvidenceService(object):
    VALID_KINDS = ("primary", "before", "after")

    def __init__(self, project_dir, evidence_dir=None):
        self.project_dir = os.path.realpath(os.path.abspath(project_dir))
        configured_root = evidence_dir or os.path.join(
            self.project_dir,
            "data",
            "evidence",
        )
        self.evidence_dir = os.path.realpath(
            os.path.abspath(configured_root)
        )

    def add_urls(self, event):
        payload = dict(event)
        urls = {}
        event_id = quote(str(event["event_id"]), safe="")
        for kind in self.VALID_KINDS:
            stored_path = self._stored_path(event, kind)
            if stored_path:
                urls[kind] = (
                    "/api/v1/events/{0}/evidence/{1}".format(
                        event_id,
                        kind,
                    )
                )
        payload["evidence_urls"] = urls
        return payload

    def resolve(self, event, kind):
        kind = str(kind)
        if kind not in self.VALID_KINDS:
            raise EvidenceNotFound("unsupported evidence kind")

        stored_path = self._stored_path(event, kind)
        if not stored_path or os.path.isabs(stored_path):
            raise EvidenceNotFound("evidence path is unavailable")

        candidate = os.path.realpath(
            os.path.abspath(
                os.path.join(self.project_dir, stored_path)
            )
        )
        try:
            common_root = os.path.commonpath(
                [self.evidence_dir, candidate]
            )
        except ValueError:
            raise EvidenceNotFound("evidence path is outside root")

        if common_root != self.evidence_dir:
            raise EvidenceNotFound("evidence path is outside root")
        if not os.path.isfile(candidate):
            raise EvidenceNotFound("evidence file does not exist")
        if os.path.splitext(candidate)[1].lower() not in (
            ".jpg",
            ".jpeg",
        ):
            raise EvidenceNotFound("unsupported evidence file type")
        return candidate

    @staticmethod
    def _stored_path(event, kind):
        if kind == "primary":
            return event.get("evidence_path")
        details = event.get("details") or {}
        return details.get("{0}_evidence_path".format(kind))
