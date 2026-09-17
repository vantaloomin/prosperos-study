import os
from typing import Protocol

import keyring
from keyring.errors import KeyringError

from server.errors import DomainError
from server.providers.config import ENV_KEYS


class CredentialVault(Protocol):
    def get(self, reference: str) -> str | None: ...
    def put(self, reference: str, secret: str) -> None: ...


class SystemVault:
    service = "Roleplay Interface"

    def get(self, reference: str) -> str | None:
        try:
            return keyring.get_password(self.service, reference)
        except KeyringError as error:
            raise DomainError("The OS credential vault is unavailable. Check your keyring setup.", 503) from error

    def put(self, reference: str, secret: str) -> None:
        try:
            keyring.set_password(self.service, reference, secret)
        except KeyringError as error:
            raise DomainError("Could not save the key in the OS credential vault.", 503) from error


def credential_for(vault: CredentialVault, provider: str, reference: str | None) -> str | None:
    if reference:
        return vault.get(reference)
    return os.environ.get(ENV_KEYS.get(provider, "ROLEPLAY_UNUSED_KEY"))
