from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "stocks"
    sqlite_url: str = "sqlite:///./stocks.db"
    pg_url: str = "postgresql+psycopg://stocks:stocks@localhost:5432/stocks"


settings = Settings()
