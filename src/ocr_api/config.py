from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_key: str | None = None
    torch_device: str = "cuda"
    max_concurrent_jobs: int = 1


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
