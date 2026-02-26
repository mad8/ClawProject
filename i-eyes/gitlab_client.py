"""
I-Eyes GitLab Client
Handles all interactions with the GitLab API.
"""

import logging
from typing import Optional

import requests

from config import Config

logger = logging.getLogger("i-eyes.gitlab")


class GitLabClient:
    def __init__(self):
        self.base_url = Config.GITLAB_URL.rstrip("/")
        self.headers = {"PRIVATE-TOKEN": Config.GITLAB_TOKEN}

    def _api(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}/api/v4{endpoint}"
        resp = requests.request(method, url, headers=self.headers, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp

    # ── Merge Request info ──────────────────────────────────────────

    def get_mr(self, project_id: int, mr_iid: int) -> dict:
        return self._api("GET", f"/projects/{project_id}/merge_requests/{mr_iid}").json()

    def get_mr_changes(self, project_id: int, mr_iid: int) -> dict:
        return self._api("GET", f"/projects/{project_id}/merge_requests/{mr_iid}/changes").json()

    def get_mr_diffs(self, project_id: int, mr_iid: int) -> list[dict]:
        """Return the list of diff entries for a MR."""
        data = self.get_mr_changes(project_id, mr_iid)
        return data.get("changes", [])

    # ── Comments / Discussions ──────────────────────────────────────

    def post_mr_note(self, project_id: int, mr_iid: int, body: str) -> dict:
        """Post a general note (comment) on the MR."""
        return self._api(
            "POST",
            f"/projects/{project_id}/merge_requests/{mr_iid}/notes",
            json={"body": body},
        ).json()

    def post_mr_discussion(
        self,
        project_id: int,
        mr_iid: int,
        body: str,
        file_path: str,
        new_line: int,
        base_sha: str,
        start_sha: str,
        head_sha: str,
        old_line: Optional[int] = None,
    ) -> dict:
        """Post an inline discussion (line-level comment) on the MR diff."""
        position = {
            "position_type": "text",
            "base_sha": base_sha,
            "start_sha": start_sha,
            "head_sha": head_sha,
            "new_path": file_path,
            "old_path": file_path,
            "new_line": new_line,
        }
        if old_line is not None:
            position["old_line"] = old_line

        return self._api(
            "POST",
            f"/projects/{project_id}/merge_requests/{mr_iid}/discussions",
            json={"body": body, "position": position},
        ).json()

    def post_mr_label(self, project_id: int, mr_iid: int, labels: list[str]) -> dict:
        """Add labels to a MR."""
        current = self.get_mr(project_id, mr_iid)
        existing = current.get("labels", [])
        merged = list(set(existing + labels))
        return self._api(
            "PUT",
            f"/projects/{project_id}/merge_requests/{mr_iid}",
            json={"labels": ",".join(merged)},
        ).json()
