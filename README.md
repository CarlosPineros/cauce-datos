# ETL de ventas por capas

Pipeline ETL en Python que extrae datos de **Amazon S3** (o archivo local), los **limpia**, los **transforma**, aplica un **modelo descriptivo** y un **modelo matemático** (regresión lineal múltiple) y carga los resultados en **PostgreSQL**. Incluye conexiones reutilizables a PostgreSQL, S3 y Azure CLI.

```
S3 / archivo ─► extraer ─► limpiar ─► transformar ─┬─► describir ──┐
                                                   └─► modelar ────┴─► cargar ─► PostgreSQL
```

## Arquitectura

Arquitectura por capas; las dependencias siempre apuntan hacia el dominio.

| Capa | Carpeta | Responsabilidad |
|---|---|---|
| Dominio | `etl/domain` | Entidades, contratos (`DataExtractor`, `DataLoader`, `PipelineStep`), errores y validadores de seguridad. Sin dependencias externas. |
| Aplicación | `etl/application` | Limpieza, transformaciones, modelo descriptivo, regresión, funciones recursivas, pasos y **orquestador**. |
| Infraestructura | `etl/infrastructure` | Adaptadores concretos: lectura de S3 y archivos locales, carga en PostgreSQL. |
| Presentación | `etl/presentation` | CLI y raíz de composición (único lugar que conecta las clases concretas). |
| Soporte | `config/`, `connections/` | Configuración desde `.env` y clientes reutilizables de PostgreSQL, S3 y Azure CLI. |

### Principios SOLID

- **S**: cada clase tiene una responsabilidad (`DataCleaner` solo limpia, `LinearRegressionModel` solo modela, cada `PipelineStep` envuelve un servicio).
- **O**: nuevas transformaciones (`FeatureTransform`), pasos (`PipelineStep`), fuentes o destinos se agregan creando clases nuevas, sin modificar las existentes.
- **L**: cualquier `DataExtractor`/`DataLoader` es intercambiable (en las pruebas se usan versiones en memoria).
- **I**: interfaces pequeñas y específicas (extraer, cargar, ejecutar).
- **D**: el orquestador y los pasos dependen de abstracciones; las implementaciones se inyectan desde `etl/presentation/ventas_pipeline.py`.

### Orquestador

`PipelineOrchestrator` registra los pasos con sus dependencias y **construye la cola de ejecución** mediante un ordenamiento topológico **recursivo** (DFS) que detecta ciclos y dependencias inexistentes. Ejecuta la cola con reintentos y backoff exponencial; si un paso falla, los siguientes se marcan como omitidos y se devuelve un reporte.

### Funciones recursivas (`etl/application/recursion.py`)

| Función | Uso |
|---|---|
| `flatten_dict` | Aplana JSON anidado (`{"ubicacion": {"region": ...}}` → `ubicacion_region`). |
| `remove_outliers_zscore` | Elimina atípicos por z-score; se repite sobre el resultado para detectar atípicos enmascarados. |
| `median_split_breakpoints` | Divide recursivamente por la mediana para segmentar en 2^n grupos. |
| `assign_segment` | Búsqueda binaria recursiva del segmento de cada valor. |
| `PipelineOrchestrator._visit` | DFS recursivo que construye la cola de ejecución. |

Todas tienen un límite de profundidad para evitar agotar la pila con entradas maliciosas.

### Modelos

- **Descriptivo**: media, mediana, moda, desviación, varianza, cuartiles, IQR, coeficiente de variación, asimetría, curtosis, correlaciones de Pearson y agregados por región.
- **Matemático**: regresión lineal múltiple por mínimos cuadrados (SVD vía `numpy.linalg.lstsq`), con R², R² ajustado, RMSE, MAE, detección de colinealidad, predicciones y residuos.

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows   |   source .venv/bin/activate  (Linux/macOS)
pip install -r requirements-dev.txt
pre-commit install
copy .env.example .env            # y completa tus credenciales
```

## Uso

```bash
python scripts/generar_datos_demo.py           # sube datos de ejemplo a S3
python -m etl                                   # S3 -> PostgreSQL (base definida en .env)
python -m etl --entorno preproduccion
python -m etl --fuente local --ruta ventas.json # lee ./data/ventas.json
python -m etl --sin-carga                       # sin escribir en la base de datos
python -m etl --entorno produccion --confirmar-produccion
python main.py                                  # verifica las conexiones
```

Tablas generadas (esquema `etl`): `ventas_datos`, `ventas_estadisticas`, `ventas_correlaciones`, `ventas_por_region`, `ventas_modelo_historico`, `ventas_limpieza_historico`.

## Seguridad

- **Credenciales** solo en `.env` (ignorado por git y bloqueado por un hook de pre-commit); se manejan como `SecretStr` y nunca se registran en logs.
- **SQL injection**: esquemas, tablas y columnas se validan con lista blanca y se componen con `psycopg.sql.Identifier`; los valores viajan por `COPY`, nunca concatenados.
- **Path traversal**: las rutas locales y claves de S3 se validan y se restringen al directorio permitido.
- **Agotamiento de recursos**: límite de tamaño de archivos y de profundidad de recursión.
- **Deserialización**: solo CSV/JSON; no se usa `pickle`, `eval` ni YAML inseguro.
- Escritura en `produccion` requiere `--confirmar-produccion`.

## Calidad

```bash
pytest                       # pruebas unitarias y de integración
ruff check .                 # linter
bandit -c pyproject.toml -r config connections etl scripts
pip-audit -r requirements.txt
pre-commit run --all-files   # todo lo anterior + detección de secretos
```

La integración continua está configurada para **GitHub Actions** (`.github/workflows/ci.yml`) y **Azure DevOps** (`azure-pipelines.yml`).
