from pathlib import Path

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

_SERVER_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SERVER_ROOT.parent


class _NonEmptyEnv(PydanticBaseSettingsSource):
    """Wrap the env source but drop empty-string values.

    Tooling (e.g. Claude Code) can export ANTHROPIC_API_KEY="" into the
    process env; left alone that empty value shadows the real key in .env,
    since process env normally outranks the dotenv source. Filtering empties
    lets the .env value win while still honoring a real exported override.
    """

    def __init__(self, inner: PydanticBaseSettingsSource):
        self._inner = inner
        super().__init__(inner.settings_cls)

    def get_field_value(self, field, field_name):  # pragma: no cover - unused
        return self._inner.get_field_value(field, field_name)

    def __call__(self) -> dict:
        return {k: v for k, v in self._inner().items() if v != ""}


class Settings(BaseSettings):
    # Load repo-root .env first, then server/.env (later wins) — by absolute
    # path so the key is found regardless of the process's working directory.
    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", _SERVER_ROOT / ".env"),
        extra="ignore",
    )

    app_name: str = "stocks"
    sqlite_url: str = "sqlite:///./stocks.db"
    pg_url: str = "postgresql+psycopg://stocks:stocks@localhost:5433/stocks"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-7"

    # Fernet key for encrypting stored credentials. Auto-generated and
    # persisted to server/.env on first use if left empty (see app/crypto.py).
    credential_key: str = ""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            _NonEmptyEnv(env_settings),
            dotenv_settings,
            file_secret_settings,
        )


settings = Settings()
