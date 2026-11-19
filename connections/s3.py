"""
Cliente reutilizable para Amazon S3 usando boto3.

Uso:
    from connections import S3Client

    s3 = S3Client()                                  # usa AWS_S3_BUCKET por defecto
    s3.upload_file("local/reporte.csv", "reportes/2026/reporte.csv")
    s3.download_file("reportes/2026/reporte.csv", "descargas/reporte.csv")
    keys = s3.list_keys(prefix="reportes/")
    url = s3.presigned_url("reportes/2026/reporte.csv", expires_in=3600)
    s3.put_object("datos/hola.txt", b"hola mundo")
    contenido = s3.get_object("datos/hola.txt")
"""
from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from config import AWSSettings, get_settings

logger = logging.getLogger(__name__)


class S3Client:
    def __init__(
        self,
        bucket: Optional[str] = None,
        settings: Optional[AWSSettings] = None,
    ) -> None:
        self.settings = settings or get_settings().aws
        self.bucket = bucket or self.settings.s3_bucket
        self._client = None

    # -------------------------------------------------------------- client
    @property
    def client(self):
        if self._client is None:
            self._client = self._build_session().client(
                "s3",
                endpoint_url=self.settings.s3_endpoint_url or None,
                config=Config(retries={"max_attempts": 5, "mode": "standard"}),
            )
        return self._client

    def _build_session(self) -> boto3.session.Session:
        s = self.settings
        # botocore lee AWS_PROFILE del entorno por su cuenta; si está vacío falla
        # con ProfileNotFound(""), así que se descarta.
        if os.environ.get("AWS_PROFILE", None) == "":
            os.environ.pop("AWS_PROFILE")
        secret =s.secret_access_key.get_secret_value() if s.secret_access_key else ""
        token = s.session_token.get_secret_value() if s.session_token else ""
        if s.access_key_id and secret:
            return boto3.session.Session(
                aws_access_key_id=s.access_key_id,
                aws_secret_access_key=secret,
                aws_session_token=token or None,
                region_name=s.region,
            )
        # Cadena estándar: perfil, variables de entorno, ~/.aws, rol IAM...
        return boto3.session.Session(profile_name=s.profile or None, region_name=s.region)

    def _bucket(self, bucket: Optional[str]) -> str:
        b = bucket or self.bucket
        if not b:
            raise ValueError("No se indicó bucket. Pásalo como argumento o define AWS_S3_BUCKET.")
        return b

    # ------------------------------------------------------------ archivos
    def upload_file(self, local_path: str | Path, key: str, bucket: Optional[str] = None,
                    extra_args: Optional[dict] = None) -> str:
        b = self._bucket(bucket)
        self.client.upload_file(str(local_path), b, key, ExtraArgs=extra_args)
        logger.info("Subido %s -> s3://%s/%s", local_path, b, key)
        return f"s3://{b}/{key}"

    def download_file(self, key: str, local_path: str | Path, bucket: Optional[str] = None) -> Path:
        b = self._bucket(bucket)
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(b, key, str(local_path))
        logger.info("Descargado s3://%s/%s -> %s", b, key, local_path)
        return local_path

    def put_object(self, key: str, data: bytes | str, bucket: Optional[str] = None,
                   content_type: Optional[str] = None) -> None:
        if isinstance(data, str):
            data = data.encode("utf-8")
        kwargs = {"Bucket": self._bucket(bucket), "Key": key, "Body": data}
        if content_type:
            kwargs["ContentType"] = content_type
        self.client.put_object(**kwargs)

    def get_object(self, key: str, bucket: Optional[str] = None, max_bytes: Optional[int] = None) -> bytes:
        """
        Descarga un objeto a memoria. Con `max_bytes` se rechazan objetos mayores
        (protege contra agotamiento de memoria). Se valida tanto el tamaño declarado
        como lo realmente leído, por si el objeto cambia entre ambas operaciones.
        """
        resp = self.client.get_object(Bucket=self._bucket(bucket), Key=key)
        if max_bytes is None:
            return resp["Body"].read()
        declared = int(resp.get("ContentLength") or 0)
        if declared > max_bytes:
            resp["Body"].close()
            raise ValueError(f"Objeto {key!r} excede el límite ({declared} > {max_bytes} bytes)")
        data = resp["Body"].read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError(f"Objeto {key!r} excede el límite de {max_bytes} bytes")
        return data

    def delete(self, key: str, bucket: Optional[str] = None) -> None:
        self.client.delete_object(Bucket=self._bucket(bucket), Key=key)

    def exists(self, key: str, bucket: Optional[str] = None) -> bool:
        try:
            self.client.head_object(Bucket=self._bucket(bucket), Key=key)
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    # ------------------------------------------------------------ listados
    def iter_objects(self, prefix: str = "", bucket: Optional[str] = None) -> Iterator[dict]:
        """Itera todos los objetos (maneja paginación automáticamente)."""
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket(bucket), Prefix=prefix):
            yield from page.get("Contents", [])

    def list_keys(self, prefix: str = "", bucket: Optional[str] = None) -> list[str]:
        return [obj["Key"] for obj in self.iter_objects(prefix, bucket)]

    def list_buckets(self) -> list[str]:
        return [b["Name"] for b in self.client.list_buckets().get("Buckets", [])]

    # --------------------------------------------------------------- otros
    def presigned_url(self, key: str, expires_in: int = 3600, bucket: Optional[str] = None,
                      method: str = "get_object") -> str:
        return self.client.generate_presigned_url(
            method,
            Params={"Bucket": self._bucket(bucket), "Key": key},
            ExpiresIn=expires_in,
        )

    def ping(self, bucket: Optional[str] = None) -> bool:
        try:
            self.client.head_bucket(Bucket=self._bucket(bucket))
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("S3 no disponible: %s", exc)
            return False
