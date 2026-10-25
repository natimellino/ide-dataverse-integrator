from typing import Any

from pydantic import BaseModel, Field


class MetadataDiff(BaseModel):
    """Diferencias entre dos ``MetadataRecord``.

    Cada entrada de ``changed_fields`` es ``clave -> (valor_target, valor_source)``.
    La convención en el flujo GN→DV es ``(valor_dv, valor_gn)`` (target primero,
    source segundo). El modelo no fija la dirección: el comparador puede invertir
    los argumentos para reusarlo si se quiere implementar el flujo inverso (DV→GN).
    """

    changed_fields: dict[str, tuple[Any, Any]] = Field(default_factory=dict)

    @property
    def has_changes(self) -> bool:
        return bool(self.changed_fields)
