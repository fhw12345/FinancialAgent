"""Single-row, atomic local credential store, independent of pi/gh/Mongo.

The directory is private (0700), SQLite file 0600 on POSIX. This is permission
protection, not application-layer encryption. A host account remains trusted.
"""

import json
import os
import sqlite3
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field, SecretStr

from .catalog import CopilotModel
from .protocol import CopilotError


class DeviceAttempt(BaseModel):
    attempt_id: str
    device_code: SecretStr
    user_code: str
    expires_at: float
    interval: float
    next_poll: float
    state: str = "pending"


class CredentialState(BaseModel):
    revision: int = 0
    generation: str = Field(default_factory=lambda: uuid4().hex)
    github_token: SecretStr = Field(default_factory=lambda: SecretStr(""))
    access_token: SecretStr = Field(default_factory=lambda: SecretStr(""))
    expires_at: float = 0
    issued_at: float = 0
    token_revision: int = 0
    base_url: str = "https://api.individual.githubcopilot.com"
    selected_model: str | None = None
    models: list[CopilotModel] = Field(default_factory=list)
    catalog_at: float = 0
    device: DeviceAttempt | None = None

    def private_json(self) -> str:
        """For private persistence ONLY, never API/export/log serialization."""
        data = self.model_dump(mode="json")
        data["github_token"] = self.github_token.get_secret_value()
        data["access_token"] = self.access_token.get_secret_value()
        if self.device:
            data["device"]["device_code"] = self.device.device_code.get_secret_value()
        return json.dumps(data)


class CopilotStore:
    def __init__(self, directory: Path) -> None:
        self.path = directory / "credentials.sqlite3"

    def _connect(self) -> sqlite3.Connection:
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if self.path.is_symlink() or self.path.parent.is_symlink():
                raise CopilotError("unsafe_credential_path")
            os.chmod(self.path.parent, 0o700)
            fd = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(fd)
            os.chmod(self.path, 0o600)
            connection = sqlite3.connect(self.path, timeout=2)
            connection.execute(
                "CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER, payload TEXT)"
            )
            connection.execute(
                "INSERT OR IGNORE INTO state VALUES (1, 0, ?)",
                (CredentialState().private_json(),),
            )
            connection.commit()
            return connection
        except (OSError, sqlite3.Error):
            raise CopilotError("credential_storage_unavailable") from None

    def read(self) -> CredentialState:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT revision, payload FROM state WHERE id=1"
            ).fetchone()
            state = CredentialState.model_validate_json(row[1])
            state.revision = row[0]
            return state
        except (ValueError, sqlite3.Error, TypeError):
            raise CopilotError("credential_storage_invalid") from None
        finally:
            connection.close()

    def save(self, state: CredentialState) -> None:
        connection = self._connect()
        try:
            updated = connection.execute(
                "UPDATE state SET revision=revision+1, payload=? WHERE id=1 AND revision=?",
                (state.private_json(), state.revision),
            )
            if updated.rowcount != 1:
                raise CopilotError("session_changed", 409)
            connection.commit()
            state.revision += 1
        except sqlite3.Error:
            raise CopilotError("credential_storage_unavailable") from None
        finally:
            connection.close()

    def clear(self) -> None:
        old = self.read()
        self.save(CredentialState(revision=old.revision))
