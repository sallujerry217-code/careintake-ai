from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    app_env: str = 'development'
    database_url: str = 'sqlite:///./careintake.db'
    admin_api_key: str = ''
    vapi_secret: str = ''
    cors_origins: str = 'http://localhost:5173'
    signing_secret: str = 'development-only-change-before-deployment'
    phone_number: str = ''
    vapi_assistant_id: str = ''
    log_level: str = 'INFO'
    audit_payloads: bool = False
    store_transcripts: bool = False
    static_dir: str = '../frontend/dist'

@lru_cache
def settings():
    cfg = Settings()
    if cfg.app_env == 'production':
        if not cfg.admin_api_key or not cfg.vapi_secret or len(cfg.signing_secret) < 32 or cfg.signing_secret.startswith('development'):
            raise RuntimeError('Production requires ADMIN_API_KEY, VAPI_SECRET and a random SIGNING_SECRET (32+ characters).')
        if cfg.database_url.startswith('sqlite'):
            raise RuntimeError('Use persistent PostgreSQL for production.')
    return cfg
