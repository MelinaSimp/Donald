from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Auth
    bearer_token: str

    # APIs
    anthropic_api_key: str
    deepgram_api_key: str
    elevenlabs_api_key: str

    # Optional: Google APIs (stubbed if not provided)
    google_calendar_credentials_json: str = ""
    gmail_credentials_json: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Database
    db_path: str = "donald.db"

    # TTS
    tts_cache_ttl_seconds: int = 300

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
