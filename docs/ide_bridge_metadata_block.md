# Bloque de metadatos `ideBridge`

Bloque personalizado de Dataverse que almacena los campos de trazabilidad
entre GeoNetwork y Dataverse. Es requisito para que la herramienta pueda
identificar registros ya sincronizados y mantener la conciliación.

## Campos

| typeName | Título | Descripción | Facetable | Busq. avanzada |
|---|---|---|---|---|
| `geonetworkUuid` | GeoNetwork UUID | UUID del registro original en GeoNetwork | Sí | Sí |
| `parentGeonetworkUuid` | Parent GeoNetwork UUID | UUID del padre (permite reconstruir la jerarquía) | Sí | Sí |
| `geoserverLayerName` | GeoServer Layer Name | Nombre calificado de la capa en GeoServer | No | No |
| `checksumMd5` | Checksum MD5 | Hash MD5 del archivo de datos | No | No |
| `modified` | Fecha de última actualización | Fecha de la última actualización del metadato en GeoNetwork | No | No |
| `status` | Estado del recurso | Estado del recurso según el Perfil IDE (ej: `completed`, `onGoing`) | No | No |
| `purpose` | Propósito | Propósito o justificación de la creación del recurso (`textbox`) | No | No |
| `resolutionScaleDenominator` | Escala | Denominador de la escala equivalente (ej: 50000 para 1:50000) | No | No |
| `maintenanceFrequency` | Frecuencia de mantenimiento | Frecuencia de actualización del recurso (ej: `asNeeded`, `annually`) | No | No |
| `lineage` | Linaje | Descripción del linaje o genealogía de los datos (`textbox`) | No | No |

`geonetworkUuid` y `parentGeonetworkUuid` son facetables y buscables para
que la Search API de Dataverse pueda filtrar por ellos durante la fase de
conciliación.

## Instalación en Dataverse (Docker)

### 1. Cargar el bloque TSV

```bash
curl http://localhost:8081/api/admin/datasetfield/load \
  -H "Content-type: text/tab-separated-values" \
  -X POST --upload-file metadata_blocks/ide_bridge.tsv
```

### 2. Asignar el bloque a la colección

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '["citation", "geospatial", "ideBridge"]' \
  "http://localhost:8081/api/dataverses/area-sensores-remotos/metadatablocks"
```

> Incluir todos los bloques que ya estén asignados (`citation`,
> `geospatial`, etc.) porque este endpoint **reemplaza** la lista completa.

### 3. Actualizar el schema de Solr

Dataverse almacena los datasets pero Solr necesita conocer los campos nuevos
para poder indexarlos. Sin este paso los datasets se crean (201) pero Solr
loguea `unknown field 'geonetworkUuid'` y no los indexa.

El procedimiento oficial usa `update-fields.sh` del contenedor `configbaker`,
que lee la lista de campos generada por Dataverse y los mergea
automáticamente en el `schema.xml` activo de Solr:

```bash
# Generar los campos desde Dataverse y mergearlos en el schema de Solr.
# El volumen montado debe apuntar a donde Solr tiene los datos del core.
curl "http://localhost:8081/api/admin/index/solr/schema" | \
  docker run -i --rm \
    -v /ruta/a/dataverse/data/solr/conf/conf/schema.xml:/schema.xml \
    gdcc/configbaker:unstable \
    update-fields.sh /schema.xml

# Recargar el core de Solr para que tome el schema actualizado
curl "http://localhost:8983/solr/admin/cores?action=RELOAD&core=collection1"
```

> **Nota sobre volúmenes:** en nuestro `compose.yml`, `./data/solr/data`
> se monta como `/var/solr` en el contenedor de Solr. `solr-precreate`
> copia el template a `/var/solr/data/collection1/conf/` sólo al crear el
> core. Después, el schema activo vive ahí y los cambios al template
> (`./data/solr/conf/`) no se propagan automáticamente.

### 4. Re-indexar datasets existentes (opcional)

Si ya existían datasets creados antes de actualizar el schema:

```bash
curl "http://localhost:8081/api/admin/index"
```

### 5. Verificar

```bash
# Verificar que el bloque está cargado en Dataverse
curl "http://localhost:8081/api/metadatablocks/ideBridge"

# Verificar que Solr conoce los campos
curl "http://localhost:8983/solr/collection1/schema/fields" | \
  python3 -m json.tool | grep geonetwork
```

## Agregar o modificar campos

Si en el futuro se extiende el bloque (ej. agregar campos nuevos al TSV):

1. Editar `metadata_blocks/ide_bridge.tsv` con los campos nuevos.
2. Re-ejecutar el paso 1 (cargar el TSV). Dataverse actualiza el bloque
   existente; no hace falta borrarlo primero.
3. Re-ejecutar el paso 3 (`update-fields.sh`). El script detecta los
   campos que faltan en el `schema.xml` y los agrega.
4. Recargar el core de Solr (paso 3, segundo comando).
5. Si los campos nuevos aplican a datasets ya creados, re-indexar (paso 4).

## Uso con easyDataverse

Una vez cargado, easyDataverse genera dinámicamente los atributos:

```python
from easyDataverse import Dataverse

dv = Dataverse(server_url="http://localhost:8081", api_token="...")
dataset = dv.create_dataset()

# Verificar nombres generados
dataset.ideBridge.info()

# Asignar valores
dataset.ideBridge.geonetwork_uuid = "8f2b3c4d-..."
dataset.ideBridge.parent_geonetwork_uuid = "1a2b3c4d-..."
```

> **Nota:** los nombres Python exactos dependen de la lógica de
> `find_common_name_part()` de easyDataverse. Verificar siempre con
> `.info()` tras cargar el bloque por primera vez.
