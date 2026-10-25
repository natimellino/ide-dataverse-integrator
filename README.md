# ide-dataverse-integrator

CLI que publica en Dataverse los metadatos de registros de GeoNetwork.

## Setup

```bash
python3 -m venv env
source env/bin/activate
pip install -e '.[dev]'
cp .env.example .env  # completar credenciales
```

## Uso

```bash
env/bin/idetool sync <uuid>            # publica el record en Dataverse
env/bin/idetool sync <uuid> --dry-run  # muestra el record mapeado sin publicar
```

## Tests

```bash
env/bin/pytest
env/bin/ruff check .
```
