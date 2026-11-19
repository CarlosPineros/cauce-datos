"""
Wrapper reutilizable sobre Azure CLI (`az`).

Requiere tener instalado Azure CLI:
    https://learn.microsoft.com/cli/azure/install-azure-cli

Uso:
    from connections import AzureCLI

    az = AzureCLI()
    az.login()                                   # SP si hay credenciales en .env, si no usa sesión actual
    cuenta = az.run("account", "show")           # -> dict (salida JSON)
    grupos = az.run("group", "list")             # -> list[dict]
    az.run("storage", "account", "list", "--resource-group", "mi-rg")
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess  # nosec B404 - se usa sin shell y con lista de argumentos
from typing import Any, Optional

from config import AzureSettings, get_settings

logger = logging.getLogger(__name__)


class AzureCLIError(RuntimeError):
    def __init__(self, cmd: list[str], returncode: int, stderr: str) -> None:
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"az falló ({returncode}): {stderr.strip()}")


class AzureCLI:
    def __init__(self, settings: Optional[AzureSettings] = None) -> None:
        self.settings = settings or get_settings().azure
        self.executable = self._find_executable()

    def _find_executable(self) -> str:
        # En Windows el ejecutable es `az.cmd`; shutil.which lo resuelve.
        path = self.settings.cli_path or shutil.which("az") or shutil.which("az.cmd")
        if not path:
            raise FileNotFoundError(
                "No se encontró Azure CLI. Instálalo o define AZURE_CLI_PATH en .env"
            )
        return path

    # ---------------------------------------------------------------- core
    def run(self, *args: str, output_json: bool = True, check: bool = True) -> Any:
        """
        Ejecuta `az <args>`. Si output_json=True agrega `--output json` y
        devuelve el resultado parseado; si no, devuelve el texto plano.
        """
        cmd = [self.executable, *args]
        if output_json and "--output" not in args and "-o" not in args:
            cmd += ["--output", "json"]

        logger.debug("Ejecutando: %s", self._mask(cmd))
        # Seguro: lista de argumentos (sin shell=True) y ejecutable resuelto con shutil.which.
        result = subprocess.run(  # noqa: S603  # nosec B603
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=self.settings.cli_timeout,
        )
        if check and result.returncode != 0:
            raise AzureCLIError(self._mask(cmd), result.returncode, result.stderr)

        out = result.stdout.strip()
        if not output_json:
            return out
        return json.loads(out) if out else None

    # ---------------------------------------------------------- sesiones
    def login(self) -> Any:
        """Login con Service Principal si está configurado; si no, valida la sesión actual."""
        s = self.settings
        if s.uses_service_principal:
            logger.info("Login en Azure con Service Principal %s", s.client_id)
            result = self.run(
                "login", "--service-principal",
                "--username", s.client_id,
                "--password", s.client_secret.get_secret_value(),
                "--tenant", s.tenant_id,
            )
        else:
            if not self.is_logged_in():
                raise AzureCLIError(
                    ["az", "account", "show"], 1,
                    "No hay sesión activa. Ejecuta `az login` o configura AZURE_CLIENT_* en .env",
                )
            result = self.account()

        if s.subscription_id:
            self.set_subscription(s.subscription_id)
        return result

    def logout(self) -> None:
        self.run("logout", output_json=False, check=False)

    def is_logged_in(self) -> bool:
        try:
            self.run("account", "show")
            return True
        except AzureCLIError:
            return False

    def account(self) -> dict:
        return self.run("account", "show")

    def set_subscription(self, subscription_id: str) -> None:
        self.run("account", "set", "--subscription", subscription_id, output_json=False)

    # ------------------------------------------------------------- utils
    def get_access_token(self, resource: Optional[str] = None) -> str:
        args = ["account", "get-access-token"]
        if resource:
            args += ["--resource", resource]
        return self.run(*args)["accessToken"]

    def version(self) -> dict:
        return self.run("version")

    @staticmethod
    def _mask(cmd: list[str]) -> list[str]:
        """Oculta el valor de --password en logs y errores."""
        masked = list(cmd)
        for i, part in enumerate(masked[:-1]):
            if part in ("--password", "-p"):
                masked[i + 1] = "****"
        return masked
