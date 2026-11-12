from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ReviewIQ"
    database_url: str
    max_upload_mb: int = 25
    upload_dir: str = "../data/uploads"
    default_workspace_name: str = "Default workspace"
    job_demo_delay: float = 1.0
    sentiment_model: str = "tabularisai/multilingual-sentiment-analysis"

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
