from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    APP_NAME: str = "Sankofa-Systems"
    DEBUG: bool = True
    OPENALEX_API_KEY: str = ""
    PUBMED_EMAIL: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
