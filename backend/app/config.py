from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=WORKSPACE_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_data_dir: Path = Path(".local")
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1024, le=65535)
    app_cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    azure_openai_base_url: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_key: SecretStr = SecretStr("")
    azure_openai_timeout_seconds: int = Field(default=60, ge=1, le=300)
    azure_openai_live_tests_enabled: bool = False
    # Optional. Some reasoning deployments accept function tools on chat/completions
    # only with reasoning_effort="none". Leave empty to omit the field.
    azure_openai_reasoning_effort: Literal["", "none", "minimal", "low", "medium", "high"] = ""
    agent_max_steps: int = Field(default=28, ge=1, le=100)
    agent_max_model_calls: int = Field(default=28, ge=1, le=100)
    agent_max_seconds: int = Field(default=300, ge=1, le=1800)
    agent_max_total_tokens: int = Field(default=250000, ge=1, le=1000000)
    agent_max_completion_tokens: int = Field(default=1600, ge=128, le=8000)
    agent_max_context_characters: int = Field(default=100000, ge=1000, le=300000)

    @field_validator("azure_openai_base_url")
    @classmethod
    def validate_azure_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return value
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/") != "/openai/v1"
        ):
            raise ValueError("Use an HTTPS Azure OpenAI base URL ending in /openai/v1/.")
        return value.rstrip("/") + "/"

    @property
    def data_dir(self) -> Path:
        path = self.app_data_dir
        return (WORKSPACE_ROOT / path).resolve() if not path.is_absolute() else path.resolve()

    @property
    def database_url(self) -> str:
        return f"sqlite:///{(self.data_dir / 'correspondence.sqlite3').as_posix()}"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.app_cors_origins.split(",") if origin.strip()]

    @property
    def missing_azure_fields(self) -> list[str]:
        fields = {
            "AZURE_OPENAI_BASE_URL": self.azure_openai_base_url.strip(),
            "AZURE_OPENAI_DEPLOYMENT": self.azure_openai_deployment.strip(),
            "AZURE_OPENAI_API_KEY": self.azure_openai_api_key.get_secret_value().strip(),
        }
        return [name for name, value in fields.items() if not value]
