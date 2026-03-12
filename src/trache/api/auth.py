"""Authentication for Trello REST API."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class TrelloAuth:
    """API key + token authentication."""

    api_key: str
    token: str

    @classmethod
    def from_env(
        cls,
        key_env: str = "TRELLO_API_KEY",
        token_env: str = "TRELLO_TOKEN",
    ) -> TrelloAuth:
        """Load credentials from environment variables."""
        api_key = os.environ.get(key_env, "")
        token = os.environ.get(token_env, "")
        if not api_key:
            raise ValueError(f"Environment variable {key_env} not set")
        if not token:
            raise ValueError(f"Environment variable {token_env} not set")
        return cls(api_key=api_key, token=token)

    @property
    def query_params(self) -> dict[str, str]:
        """Auth params to append to API requests."""
        return {"key": self.api_key, "token": self.token}
