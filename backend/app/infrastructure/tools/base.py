from abc import ABC, abstractmethod
from typing import Type, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.domain.entities.tool import ToolPermission
from app.domain.interfaces.sandbox import SandboxInterface


class ToolResult(BaseModel):
    tool_name: str
    success: bool
    output: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BaseTool(ABC):
    name: str
    description: str
    args_schema: Type[BaseModel]
    permission_required: ToolPermission = ToolPermission.READ
    timeout_seconds: int = 30
    output_schema: Optional[Type[BaseModel]] = None

    def validate_inputs(self, kwargs: Dict[str, Any]) -> BaseModel:
        """Validate raw input dictionary against the tool's input schema."""
        return self.args_schema.model_validate(kwargs)

    @abstractmethod
    async def execute(self, sandbox: SandboxInterface, sandbox_id: str, **kwargs) -> ToolResult:
        """Execute tool logic inside sandbox environment."""
        pass

    def to_openai_schema(self) -> Dict[str, Any]:
        """Format tool schema for LLM function calling definition."""
        schema = self.args_schema.model_json_schema()
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }
