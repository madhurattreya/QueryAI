"""
backend/services/webhook_notifier.py
──────────────────────────────────────
Slack & Microsoft Teams Webhook Notifier.

Sends real-time query insights, KPI alert triggers, and scheduled report notifications
to enterprise Slack channels and Microsoft Teams webhooks.
"""

from __future__ import annotations
import json
import logging
import urllib.request
from typing import Dict, Any, Optional

logger = logging.getLogger("queryiq.webhook")

class WebhookNotifier:
    """
    Service for pushing rich notifications to Slack and Microsoft Teams.
    """

    def send_slack_notification(self, webhook_url: str, title: str, message: str, metrics: Optional[Dict[str, Any]] = None) -> bool:
        """
        Sends a formatted Slack card payload.
        """
        if not webhook_url:
            return False

        fields = []
        if metrics:
            for k, v in metrics.items():
                fields.append({"type": "mrkdwn", "text": f"*{k}:*\n{v}"})

        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": f"🚨 {title}", "emoji": True}
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": message}
                }
            ]
        }

        if fields:
            payload["blocks"].append({"type": "section", "fields": fields[:10]})

        return self._http_post(webhook_url, payload)

    def send_teams_notification(self, webhook_url: str, title: str, message: str, metrics: Optional[Dict[str, Any]] = None) -> bool:
        """
        Sends an Adaptive Card payload to Microsoft Teams.
        """
        if not webhook_url:
            return False

        facts = []
        if metrics:
            for k, v in metrics.items():
                facts.append({"name": str(k), "value": str(v)})

        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": "0076D7",
            "summary": title,
            "sections": [{
                "activityTitle": title,
                "activitySubtitle": "QueryIQ Automated Enterprise Alert",
                "text": message,
                "facts": facts
            }]
        }

        return self._http_post(webhook_url, payload)

    def _http_post(self, url: str, payload: Dict[str, Any]) -> bool:
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Failed to post webhook to {url}: {e}")
            return False


# Global singleton instance
webhook_notifier = WebhookNotifier()
