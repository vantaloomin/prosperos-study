from ipaddress import ip_address
from typing import ClassVar, Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator

from server.models import Input
from server.providers.lmstudio import native_base

Provider = Literal["openai", "anthropic", "openrouter", "local", "kobold", "codex", "google", "compatible"]
DEFAULT_URLS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "local": "http://127.0.0.1:1234/v1",
    "kobold": "http://127.0.0.1:5001/api/v1",
    "codex": "",
    "google": "https://generativelanguage.googleapis.com/v1beta",
    "compatible": "",
}
ENV_KEYS = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
            "openrouter": "OPENROUTER_API_KEY", "local": "ROLEPLAY_LOCAL_API_KEY",
            "google": "GEMINI_API_KEY", "compatible": "ROLEPLAY_COMPATIBLE_API_KEY"}


def is_loopback(host: str | None) -> bool:
    if host == "localhost":
        return True
    try:
        return ip_address(host or "").is_loopback
    except ValueError:
        return False


def validate_local_url(url: str):
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not is_loopback(parts.hostname):
        raise ValueError("Local services must use a localhost or loopback HTTP(S) address.")
    if any((parts.username, parts.password, parts.query, parts.fragment)):
        raise ValueError("Put credentials in the API key field, not in the server address.")


def validate_compatible_url(url: str):
    parts = urlsplit(url)
    if not parts.hostname or (parts.scheme != 'https' and not (parts.scheme == 'http' and is_loopback(parts.hostname))):
        raise ValueError('Use an HTTPS API base URL, or HTTP for a loopback service.')
    if any((parts.username, parts.password, parts.query, parts.fragment)):
        raise ValueError('Put credentials in the API key field, not in the server address.')
    if parts.port == 0:
        raise ValueError('Use a valid service port.')


def validate_profile_url(provider, url, allow_incomplete=False):
    if provider in {'local', 'kobold'}:
        validate_local_url(url)
    elif provider == 'compatible':
        if url or not allow_incomplete:
            validate_compatible_url(url)
    elif url != DEFAULT_URLS[provider]:
        raise ValueError('This provider uses its official API address.')


def profile_ready(config):
    return bool(config.get('model', '').strip()) and (config['provider'] == 'codex' or bool(config.get('base_url')))


class ProfileConfig(Input):
    allow_incomplete: ClassVar[bool] = False
    provider: Provider
    model: str = Field(min_length=1, max_length=200)
    base_url: str = ""
    max_output_tokens: int = Field(default=1200, ge=64, le=128000)
    context_tokens: int = Field(default=16000, ge=1024, le=2000000)
    timeout_seconds: int = Field(default=180, ge=10, le=1800)
    temperature: float | None = Field(default=None, ge=0, le=2)
    reasoning_effort: Literal["minimal", "low", "medium", "high", "xhigh"] | None = None
    local_protocol: Literal["openai", "lmstudio"] = "openai"
    local_reasoning: Literal["off", "on", "low", "medium", "high"] | None = None

    @model_validator(mode="after")
    def validate_capabilities(self):
        self.base_url = (self.base_url or DEFAULT_URLS[self.provider]).rstrip("/")
        validate_profile_url(self.provider, self.base_url, self.allow_incomplete)
        if self.provider == "codex" and self.temperature is not None:
            raise ValueError("Codex CLI does not support a temperature setting here.")
        if self.provider == "anthropic" and self.temperature is not None and self.temperature > 1:
            raise ValueError("Anthropic temperature must be between 0 and 1.")
        if self.reasoning_effort and self.provider not in {"codex", "openai"}:
            raise ValueError("This adapter does not expose a reasoning-effort setting.")
        self.validate_local_options()
        return self

    def validate_local_options(self):
        native = self.provider == 'local' and self.local_protocol == 'lmstudio'
        if self.local_protocol != 'openai' and self.provider != 'local':
            raise ValueError('The LM Studio protocol is only available for local profiles.')
        if self.local_reasoning is not None and not native:
            raise ValueError('Local reasoning control requires the LM Studio native protocol.')
        if native:
            self.base_url = native_base(self.base_url)
            if self.temperature is not None and self.temperature > 1:
                raise ValueError('LM Studio native temperature must be between 0 and 1.')


class DiscoveryConfig(ProfileConfig):
    model: str = Field(default='', max_length=200)


class ConnectionProbe(Input):
    config: DiscoveryConfig
    api_key: SecretStr | None = None
    profile_id: str | None = None
    expected_version_id: str | None = None


class SavedProfileConfig(ProfileConfig):
    allow_incomplete: ClassVar[bool] = True
    model: str = Field(default='', max_length=200)


class ProfileCreate(Input):
    name: str = Field(default='', max_length=120)
    config: SavedProfileConfig
    api_key: SecretStr | None = None
    make_primary: bool = False

    @field_validator('config', mode='before')
    @classmethod
    def accept_typed_config(cls, value):
        return value.model_dump() if isinstance(value, ProfileConfig) else value


class ProfileUpdate(ProfileCreate):
    expected_version_id: str


class PrimaryUpdate(Input):
    profile_id: str
