from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ReviewIQ"
    database_url: str
    max_upload_mb: int = 25
    upload_dir: str = "../data/uploads"
    default_workspace_name: str = "Default workspace"
    job_demo_delay: float = 1.0
    sentiment_model: str = "tabularisai/multilingual-sentiment-analysis"
    roberta_model: str = "cardiffnlp/twitter-roberta-base-sentiment-latest"
    nlptown_model: str = "nlptown/bert-base-multilingual-uncased-sentiment"
    xlmr_model: str = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
    distil_model: str = ""  # multilingual DistilBERT: verify the Hub id, then set it here or in .env
    tfidf_path: str = "../ml/out/tfidf_lr.joblib"
    extra_models: str = ""  # comma-separated Hugging Face ids to try as extra optional models
    star_model: str = "nlptown/bert-base-multilingual-uncased-sentiment"  # empty string disables it
    llm_url: str = "http://127.0.0.1:11434"
    llm_model: str = "qwen2.5:3b"
    llm_timeout: float = 180.0
    tesseract_cmd: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
