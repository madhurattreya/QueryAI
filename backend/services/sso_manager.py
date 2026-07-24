"""
backend/services/sso_manager.py
───────────────────────────────
Enterprise SSO (Single Sign-On), SAML 2.0 & OIDC Management Service.

Provides integration hooks for identity providers (Okta, Azure AD / Entra ID, Auth0, Ping Identity)
and maps IDP user groups to QueryIQ RBAC roles.
"""

from __future__ import annotations
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger("queryiq.sso")

class SSOManager:
    """
    Manages Enterprise SSO configurations, SAML/OIDC tokens, and group RBAC mapping.
    """

    def __init__(self):
        self.providers: Dict[str, Dict[str, Any]] = {
            "okta": {
                "enabled": False,
                "client_id": "",
                "issuer_url": "",
                "role_mapping": {"Admins": "admin", "Analysts": "analyst", "Users": "viewer"}
            },
            "azure_ad": {
                "enabled": False,
                "tenant_id": "",
                "client_id": "",
                "role_mapping": {}
            }
        }

    def configure_provider(self, provider_id: str, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Configures an Enterprise SSO provider (Okta, Azure AD, Auth0).
        """
        provider_key = provider_id.lower()
        self.providers[provider_key] = {
            "enabled": config_data.get("enabled", True),
            "client_id": config_data.get("client_id", ""),
            "issuer_url": config_data.get("issuer_url", ""),
            "tenant_id": config_data.get("tenant_id", ""),
            "role_mapping": config_data.get("role_mapping", {})
        }
        logger.info(f"Configured SSO provider '{provider_key}'.")
        return {"success": True, "provider": provider_key, "config": self.providers[provider_key]}

    def get_provider_config(self, provider_id: str) -> Optional[Dict[str, Any]]:
        return self.providers.get(provider_id.lower())

    def map_idp_groups_to_role(self, provider_id: str, idp_groups: List[str]) -> str:
        """
        Maps a list of IDP user groups to a QueryIQ RBAC role (admin, manager, analyst, viewer).
        """
        config = self.get_provider_config(provider_id)
        if not config:
            return "viewer"

        mapping = config.get("role_mapping", {})
        for group in idp_groups:
            if group in mapping:
                return mapping[group]

        return "viewer"


# Global singleton instance
sso_manager = SSOManager()
