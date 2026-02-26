"""
I-Eyes Webhook Server
Receives GitLab MR webhooks and triggers AI code review.
"""

import hashlib
import hmac
import logging

from flask import Flask, request, jsonify

from config import Config
from gitlab_client import GitLabClient
from reviewer import AIReviewer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("i-eyes.server")

app = Flask(__name__)
gitlab = GitLabClient()
reviewer = AIReviewer()

SEVERITY_EMOJI = {
    "ok": "✅",
    "info": "ℹ️",
    "warning": "⚠️",
    "critical": "🚨",
}


def verify_webhook(req) -> bool:
    """Verify the GitLab webhook secret token."""
    if not Config.GITLAB_WEBHOOK_SECRET:
        return True
    token = req.headers.get("X-Gitlab-Token", "")
    return hmac.compare_digest(token, Config.GITLAB_WEBHOOK_SECRET)


def format_summary_comment(result, mr_url: str) -> str:
    """Format the review summary as a Markdown comment."""
    emoji = SEVERITY_EMOJI.get(result.severity, "ℹ️")
    lines = [
        f"## {emoji} I-Eyes Code Review",
        "",
        f"**Verdict global : {result.severity.upper()}**",
        "",
        result.summary,
        "",
    ]
    if result.comments:
        lines.append(f"**{len(result.comments)} remarque(s) détaillée(s) ci-dessous.**")
    else:
        lines.append("Aucune remarque particulière. Le code semble conforme. ✅")

    lines.append("\n---\n*Revue automatique par I-Eyes 💀*")
    return "\n".join(lines)


def format_inline_comment(comment) -> str:
    """Format a single inline review comment."""
    emoji = SEVERITY_EMOJI.get(comment.severity, "ℹ️")
    return f"{emoji} **I-Eyes** [{comment.severity.upper()}]\n\n{comment.message}"


def process_merge_request(payload: dict):
    """Process a MR webhook event."""
    attrs = payload.get("object_attributes", {})
    project = payload.get("project", {})

    mr_iid = attrs.get("iid")
    project_id = project.get("id")
    action = attrs.get("action")
    mr_title = attrs.get("title", "")
    mr_description = attrs.get("description", "")
    mr_url = attrs.get("url", "")

    if action not in ("open", "reopen", "update"):
        logger.info("Ignoring MR action: %s", action)
        return {"status": "ignored", "reason": f"action={action}"}

    logger.info("Processing MR !%s (%s) in project %s", mr_iid, action, project_id)

    # Fetch diffs
    diffs = gitlab.get_mr_diffs(project_id, mr_iid)
    if not diffs:
        logger.info("No diffs found for MR !%s", mr_iid)
        return {"status": "skipped", "reason": "no diffs"}

    logger.info("Found %d changed file(s)", len(diffs))

    # AI Review
    result = reviewer.review(diffs, mr_title, mr_description)

    # Post summary comment
    summary_body = format_summary_comment(result, mr_url)
    gitlab.post_mr_note(project_id, mr_iid, summary_body)
    logger.info("Posted summary comment on MR !%s", mr_iid)

    # Post inline comments
    if result.comments:
        mr_data = gitlab.get_mr(project_id, mr_iid)
        diff_refs = mr_data.get("diff_refs", {})
        base_sha = diff_refs.get("base_sha", "")
        start_sha = diff_refs.get("start_sha", "")
        head_sha = diff_refs.get("head_sha", "")

        posted = 0
        for comment in result.comments:
            try:
                body = format_inline_comment(comment)
                gitlab.post_mr_discussion(
                    project_id=project_id,
                    mr_iid=mr_iid,
                    body=body,
                    file_path=comment.file,
                    new_line=comment.line,
                    base_sha=base_sha,
                    start_sha=start_sha,
                    head_sha=head_sha,
                )
                posted += 1
            except Exception as e:
                logger.warning(
                    "Failed to post inline comment on %s:%d — %s",
                    comment.file, comment.line, e,
                )

        logger.info("Posted %d/%d inline comments on MR !%s", posted, len(result.comments), mr_iid)

    # Add label based on severity
    if result.severity in ("warning", "critical"):
        try:
            gitlab.post_mr_label(project_id, mr_iid, [f"i-eyes:{result.severity}"])
        except Exception as e:
            logger.warning("Failed to add label: %s", e)

    return {
        "status": "reviewed",
        "severity": result.severity,
        "comments_count": len(result.comments),
    }


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "i-eyes"})


@app.route("/webhook", methods=["POST"])
def webhook():
    if not verify_webhook(request):
        logger.warning("Invalid webhook secret")
        return jsonify({"error": "unauthorized"}), 401

    event = request.headers.get("X-Gitlab-Event", "")
    if event != "Merge Request Hook":
        logger.info("Ignoring event: %s", event)
        return jsonify({"status": "ignored", "event": event})

    payload = request.json
    try:
        result = process_merge_request(payload)
        return jsonify(result)
    except Exception as e:
        logger.exception("Error processing webhook: %s", e)
        return jsonify({"error": str(e)}), 500


def main():
    Config.validate()
    logger.info("I-Eyes starting on %s:%d", Config.HOST, Config.PORT)
    app.run(host=Config.HOST, port=Config.PORT, debug=False)


if __name__ == "__main__":
    main()
