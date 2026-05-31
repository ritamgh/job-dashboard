from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_path: Path = Path('data/startup_search.db')
    fetch_cache_dir: Path = Path('data/fetch_cache')
    openai_api_key: str | None = None
    openai_analysis_model: str = 'gpt-4.1-mini'
    openai_message_model: str = 'gpt-4.1-mini'
    request_timeout_seconds: float = 12.0
    max_page_chars: int = 12000

    model_config = SettingsConfigDict(env_file='.env', env_prefix='STARTUP_SEARCH_', extra='ignore')


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    settings.fetch_cache_dir.mkdir(parents=True, exist_ok=True)
    return settings
