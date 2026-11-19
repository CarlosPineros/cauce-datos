"""
Ejemplo / chequeo rápido de las tres conexiones.

    python main.py
"""
import logging

from config import get_settings

settings = get_settings()
logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("main")


def check_postgres() -> None:
    from connections import PostgresClient

    with PostgresClient() as db:
        if not db.ping():
            raise ConnectionError("revisa POSTGRES_* en .env")
        log.info("PostgreSQL OK: %s", db.fetch_value("SELECT version()"))


def check_azure() -> None:
    from connections import AzureCLI

    az = AzureCLI()
    cuenta = az.login()
    log.info("Azure OK: suscripción activa %s", az.account().get("name") if cuenta else None)


def check_s3() -> None:
    from connections import S3Client

    s3 = S3Client()
    if not s3.ping():
        raise ConnectionError("revisa AWS_* en .env")
    log.info("S3 OK: bucket %s accesible", s3.bucket)


if __name__ == "__main__":
    for nombre, check in (("PostgreSQL", check_postgres), ("Azure", check_azure), ("S3", check_s3)):
        try:
            check()
        except Exception as exc:  # noqa: BLE001
            log.error("%s falló: %s", nombre, exc)
