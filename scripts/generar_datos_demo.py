"""
Genera un dataset sintético de ventas (JSON anidado) con errores intencionales
para probar el ETL, y lo sube a S3 (LocalStack) o lo guarda en ./data.

    python scripts/generar_datos_demo.py              # sube a s3://<bucket>/datos/ventas.json
    python scripts/generar_datos_demo.py --local      # guarda data/ventas.json
    python scripts/generar_datos_demo.py --filas 5000 --semilla 7

Modelo con el que se generan los datos (para validar la regresión):
    cantidad ≈ 20 + 0.05·gasto_publicidad − 0.08·precio_unitario + 30·descuento + ruido
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REGIONES = {
    "Norte": ["Monterrey", "Saltillo"],
    "Sur": ["Mérida", "Oaxaca"],
    "Centro": ["CDMX", "Puebla"],
    "Occidente": ["Guadalajara", "Colima"],
}
PRODUCTOS = {
    "Laptop": "tecnologia",
    "Monitor": "tecnologia",
    "Silla": "muebles",
    "Escritorio": "muebles",
    "Cafetera": "hogar",
}


def generar(filas: int, semilla: int) -> list[dict]:
    rng = np.random.default_rng(semilla)
    inicio = date(2025, 1, 1)
    registros: list[dict] = []
    for i in range(1, filas + 1):
        region = str(rng.choice(list(REGIONES)))
        producto = str(rng.choice(list(PRODUCTOS)))
        precio = float(np.round(rng.uniform(50, 400), 2))
        descuento = float(np.round(rng.choice([0, 0.05, 0.1, 0.15, 0.2]), 2))
        gasto = float(np.round(rng.gamma(4, 60), 2))
        cantidad = max(1, round(20 + 0.05 * gasto - 0.08 * precio + 30 * descuento + rng.normal(0, 3)))
        registros.append({
            "id_venta": i,
            "fecha": (inicio + timedelta(days=int(rng.integers(0, 365)))).isoformat(),
            "ubicacion": {"region": region, "ciudad": str(rng.choice(REGIONES[region]))},
            "producto": {"nombre": producto, "categoria": PRODUCTOS[producto]},
            "cantidad": cantidad,
            "precio_unitario": precio,
            "descuento": descuento,
            "gasto_publicidad": gasto,
        })
    return ensuciar(registros, rng)


def ensuciar(registros: list[dict], rng: np.random.Generator) -> list[dict]:
    """Introduce errores típicos de datos reales."""
    n = len(registros)

    def muestra(pct: float) -> np.ndarray:
        return rng.choice(n, size=max(1, int(n * pct)), replace=False)

    for i in muestra(0.03):
        registros[i]["gasto_publicidad"] = None                         # nulos
    for i in muestra(0.02):
        registros[i]["ubicacion"]["region"] = f"  {registros[i]['ubicacion']['region'].upper()} "  # formato
    for i in muestra(0.01):
        registros[i]["cantidad"] = -abs(registros[i]["cantidad"])        # fuera de rango
    for i in muestra(0.01):
        registros[i]["descuento"] = 1.5                                  # fuera de rango
    for i in muestra(0.01):
        registros[i]["gasto_publicidad"] = 50_000.0                      # atípico
    for i in muestra(0.01):
        registros[i]["fecha"] = "sin-fecha"                              # fecha inválida
    for i in muestra(0.01):
        registros[i]["precio_unitario"] = "N/A"                          # texto en numérico
    duplicados = [json.loads(json.dumps(registros[i])) for i in muestra(0.03)]
    return registros + duplicados                                        # duplicados


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--filas", type=int, default=2000)
    p.add_argument("--semilla", type=int, default=42)
    p.add_argument("--clave", default="datos/ventas.json")
    p.add_argument("--local", action="store_true", help="Guardar en ./data en lugar de S3")
    args = p.parse_args()
    if not 10 <= args.filas <= 1_000_000:
        p.error("--filas debe estar entre 10 y 1.000.000")

    payload = json.dumps(generar(args.filas, args.semilla), ensure_ascii=False, indent=1).encode("utf-8")

    if args.local:
        destino = ROOT / "data" / "ventas.json"
        destino.parent.mkdir(exist_ok=True)
        destino.write_bytes(payload)
        print(f"Guardado {destino} ({len(payload):,} bytes)")
    else:
        from connections import S3Client
        from etl.domain import validate_object_key

        s3 = S3Client()
        s3.put_object(validate_object_key(args.clave), payload, content_type="application/json")
        print(f"Subido s3://{s3.bucket}/{args.clave} ({len(payload):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
