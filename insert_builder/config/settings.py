from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_host: str = "internal-production.carmacloud.com"
    database_port: int = 3306
    database_username: str = "publisher"
    database_password: str
    database_name: str = "carma_provision"

    storage_path: str = "C:\\carma\\storage\\insert_builder"
    remote_path: str = "C:\\Dropbox"

    developer_email: str
    from_email: str = "insertbuilder@cwaustral.com.au"
    email_enabled: bool = False
    smtp_host: str = "127.0.0.1"
    smtp_port: str = "25"
    smtp_username: str = ""
    smtp_password: str = ""

    publisher_encryption_key: str = ""

settings = Settings()