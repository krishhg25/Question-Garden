from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = 'sqlite:///./question_generator.db'
    google_client_id: str = ''
    allow_demo_auth: bool = False
    demo_payments_enabled: bool = True
    cors_origins: str = 'http://localhost:5173,http://127.0.0.1:5173'
    credit_timezone: str = 'Asia/Kolkata'
    ollama_url: str = ''
    ollama_model: str = 'qwen2.5:3b'
    max_upload_mb: int = 10
    max_pages: int = 30
    max_text_chars: int = 60000
    tesseract_cmd: str = ''


settings = Settings()
