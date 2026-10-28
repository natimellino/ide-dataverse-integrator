# ide-dataverse-integrator

CLI que publica y sincroniza en Dataverse los metadatos de registros de GeoNetwork. El desarrollo de esta herramienta forma parte de la tesina final de grado para la carrera de Licenciatura en Ciencias de la Computación y su implementación está atada a las necesidades específicas que surgieron en el contexto del trabajo en cuestión.

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
