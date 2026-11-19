"""
Configuración centralizada del proyecto.

Lee variables desde el entorno y/o el archivo `.env` en la raíz del proyecto.
Cada servicio tiene su propio bloque con prefijo:

    POSTGRES_*  -> PostgresSettings
    AZURE_*     -> AzureSettings
    AWS_*       -> AWSSettings

Uso:
    from config import get_settings
    settings = get_settings()
    settings.postgres.dsn
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"


def _config(prefix: str) -> SettingsConfigDict:
    return SettingsConfigDict(
        env_prefix=prefix,
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


class PostgresSettings(BaseSettings):
    model_config = _config("POSTGRES_")

    host: str = "localhost"
    port: int = 5432
    db: str = "postgres"
    user: str = "postgres"
    password: SecretStr = SecretStr("")
    sslmode: str = "prefer"          # disable | prefer | require | verify-full
    connect_timeout: int = 10
    pool_min_size: int = 1
    pool_max_size: int = 10

    @property
    def dsn(self) -> str:
        """Cadena de conexión libpq (escapa espacios y caracteres especiales)."""
        def q(value: object) -> str:
            v = str(value).replace("\\", "\\\\").replace("'", "\\'")
            return f"'{v}'"

        parts = {
            "host": self.host,
            "port": self.port,
            "dbname": self.db,
            "user": self.user,
            "password": self.password.get_secret_value(),
            "sslmode": self.sslmode,
            "connect_timeout": self.connect_timeout,
        }
        return " ".join(f"{k}={q(v)}" for k, v in parts.items())


class AzureSettings(BaseSettings):
    model_config = _config("AZURE_")

    # Si se definen client_id/secret/tenant se usa login con Service Principal.
    # Si no, se asume una sesión existente (`az login` interactivo).
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[SecretStr] = None
    subscription_id: Optional[str] = None
    cli_path: Optional[str] = None     # ruta a az / az.cmd si no está en PATH
    cli_timeout: int = 300

    @property
    def uses_service_principal(self) -> bool:
        secret = self.client_secret.get_secret_value() if self.client_secret else ""
        return bool(self.tenant_id and self.client_id and secret)


class AWSSettings(BaseSettings):
    model_config = _config("AWS_")

    # Si se dejan vacías, boto3 usa la cadena estándar de credenciales
    # (~/.aws/credentials, perfil, rol IAM, etc.).
    access_key_id: Optional[str] = None
    secret_access_key: Optional[SecretStr] = None
    session_token: Optional[SecretStr] = None
    profile: Optional[str] = None
    region: str = "us-east-1"
    s3_bucket: Optional[str] = None          # bucket por defecto
    s3_endpoint_url: Optional[str] = None    # para MinIO / LocalStack


class Settings(BaseSettings):
    model_config = _config("APP_")

    env: str = "dev"
    log_level: str = "INFO"

    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    azure: AzureSettings = Field(default_factory=AzureSettings)
    aws: AWSSettings = Field(default_factory=AWSSettings)


@lru_cache
def get_settings() -> Settings:
    """Devuelve una instancia única (cacheada) de la configuración."""
    return Settings()
