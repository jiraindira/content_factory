from pydantic import BaseModel, ConfigDict
from typing import Any, Dict

class SchemaBase(BaseModel):
    """
    Base class for all schemas in the AI Affiliate Engine.
    Enforces strict fields and provides safe serialization.
    """

    model_config = ConfigDict(extra="forbid")

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)
