from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pydantic import BaseModel


class CommandResult(BaseModel):
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    truncated: bool = False
    runtime: str = "python"


class SandboxInterface(ABC):
    @abstractmethod
    async def create_sandbox(
        self,
        session_id: str,
        workspace_path: str = "",
        runtime: str = "python",
        env_vars: Optional[Dict[str, str]] = None,
    ) -> str:
        """Initialize and spawn an isolated container workspace."""
        pass

    @abstractmethod
    async def execute_command(
        self,
        sandbox_id: str,
        command: str,
        timeout_seconds: int = 120,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        """Run a command safely inside the sandbox container."""
        pass

    @abstractmethod
    async def read_file(self, sandbox_id: str, file_path: str) -> str:
        """Read file contents inside the sandbox environment."""
        pass

    @abstractmethod
    async def write_file(self, sandbox_id: str, file_path: str, content: str) -> bool:
        """Write file contents inside the sandbox environment."""
        pass

    @abstractmethod
    async def destroy_sandbox(self, sandbox_id: str) -> bool:
        """Terminate and clean up sandbox resources."""
        pass

