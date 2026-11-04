from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Modelo que se lee y se escribe en camelCase para el frontend y el agente."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)

    def to_json(self) -> dict:
        return self.model_dump(mode="json", by_alias=True)
