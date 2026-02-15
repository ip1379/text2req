from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    jira_base_url: str = "http://localhost:8081"
    jira_email: str = "your-jira-username"
    jira_api_token: str = "your-jira-personal-access-token"
    lm_studio_url: str = "http://localhost:1234"
    lm_studio_model: str = "default"

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
