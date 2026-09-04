from typing import Dict, List, Any, Optional
from app.infrastructure.tools.base import BaseTool
from app.infrastructure.tools.file_tools import (
    ListFilesTool,
    ReadFileTool,
    WriteFileTool,
    CreateFileTool,
    DeleteFileTool,
    SearchFilesTool,
    GetProjectStructureTool,
)
from app.infrastructure.tools.execution_tools import (
    ExecuteCommandTool,
    RunCommandTool,
    RunTestsTool,
    GetGitStatusTool,
    GetGitDiffTool,
    CreateGitBranchTool,
    CreateGitCommitTool,
    PushGitBranchTool,
)
from app.core.exceptions import ToolExecutionError


class ToolRegistry:
    """
    Registry for agent tools. Strictly registers, validates, and exposes
    all available tools. Rejects unregistered or unknown tool names.
    """

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        default_tools = [
            ListFilesTool(),
            ReadFileTool(),
            WriteFileTool(),
            CreateFileTool(),
            DeleteFileTool(),
            SearchFilesTool(),
            GetProjectStructureTool(),
            ExecuteCommandTool(),
            RunCommandTool(),  # Alias for backward compatibility
            RunTestsTool(),
            GetGitStatusTool(),
            GetGitDiffTool(),
            CreateGitBranchTool(),
            CreateGitCommitTool(),
            PushGitBranchTool(),
        ]
        for tool in default_tools:
            self._tools[tool.name] = tool

    def register_tool(self, tool: BaseTool) -> None:
        """Register a new tool into the registry."""
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> BaseTool:
        """
        Retrieve a registered tool by name.
        
        Raises ToolExecutionError if the tool name is unknown or not registered.
        """
        tool = self._tools.get(name)
        if not tool:
            raise ToolExecutionError(
                f"Security violation: Unknown tool '{name}' requested. Execution rejected."
            )
        return tool

    def has_tool(self, name: str) -> bool:
        """Check if a tool name is registered."""
        return name in self._tools

    def get_all_tools(self) -> List[BaseTool]:
        """Return list of all registered tools."""
        return list(self._tools.values())

    def get_openai_schemas(self) -> List[Dict[str, Any]]:
        """Return JSON schemas for LLM tool definitions."""
        return [tool.to_openai_schema() for tool in self._tools.values()]
