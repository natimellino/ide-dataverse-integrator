from pydantic import BaseModel, Field


class ReconciliationPlan(BaseModel):
    """Resultado de conciliar UUIDs de GeoNetwork contra Dataverse.

    Clasifica los registros en tres grupos:
    - to_create: UUIDs presentes en GeoNetwork pero no en Dataverse
    - existing: UUIDs presentes en ambos {geonetwork_uuid: persistent_id}
    - orphans: UUIDs en Dataverse pero eliminados de GeoNetwork {geonetwork_uuid: persistent_id}
    """

    to_create: list[str] = Field(default_factory=list)
    existing: dict[str, str] = Field(default_factory=dict)
    orphans: dict[str, str] = Field(default_factory=dict)

    @property
    def has_work(self) -> bool:
        return bool(self.to_create or self.orphans)
