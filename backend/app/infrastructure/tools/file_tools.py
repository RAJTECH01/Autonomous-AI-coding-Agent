import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.infrastructure.tools.base import BaseTool, ToolResult
from app.infrastructure.tools.path_validator import PathValidator
from app.domain.entities.tool import ToolPermission
from app.domain.interfaces.sandbox import SandboxInterface


# 1. list_files
class ListFilesInput(BaseModel):
    directory_path: str = Field(default=".", description="Relative path of directory to list")
    recursive: bool = Field(default=True, description="Whether to recursively list subdirectories")


class ListFilesOutput(BaseModel):
    files: List[str]
    count: int


class ListFilesTool(BaseTool):
    name = "list_files"
    description = "List files inside a directory within the workspace"
    args_schema = ListFilesInput
    permission_required = ToolPermission.READ
    timeout_seconds = 15
    output_schema = ListFilesOutput

    async def execute(self, sandbox: SandboxInterface, sandbox_id: str, **kwargs) -> ToolResult:
        validated = self.validate_inputs(kwargs)
        clean_path = PathValidator.validate_workspace_path(validated.directory_path)  # type: ignore

        try:
            flag = "-la" if validated.recursive else "-l"  # type: ignore
            res = await sandbox.execute_command(sandbox_id, f"find '{clean_path}' -maxdepth 4", timeout_seconds=15)
            if res.exit_code != 0:
                # Fallback to ls command
                res = await sandbox.execute_command(sandbox_id, f"ls {clean_path}", timeout_seconds=15)

            files_list = [f.strip() for f in res.stdout.splitlines() if f.strip()]
            return ToolResult(
                tool_name=self.name,
                success=res.exit_code == 0,
                output="\n".join(files_list),
                error=res.stderr if res.exit_code != 0 else None,
                metadata={"file_count": len(files_list), "directory_path": clean_path},
            )
        except Exception as e:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(e))


# 2. read_file
class ReadFileInput(BaseModel):
    file_path: str = Field(description="Relative path of file to read")
    start_line: Optional[int] = Field(default=None, description="Optional 1-indexed start line")
    end_line: Optional[int] = Field(default=None, description="Optional 1-indexed end line")


class ReadFileOutput(BaseModel):
    content: str
    file_path: str
    total_lines: int


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read full or slice content of a specified file in workspace"
    args_schema = ReadFileInput
    permission_required = ToolPermission.READ
    timeout_seconds = 15
    output_schema = ReadFileOutput

    async def execute(self, sandbox: SandboxInterface, sandbox_id: str, **kwargs) -> ToolResult:
        validated: ReadFileInput = self.validate_inputs(kwargs)  # type: ignore
        clean_path = PathValidator.validate_workspace_path(validated.file_path)

        try:
            content = await sandbox.read_file(sandbox_id, clean_path)
            lines = content.splitlines()
            total_lines = len(lines)

            if validated.start_line is not None or validated.end_line is not None:
                start = (validated.start_line - 1) if validated.start_line else 0
                end = validated.end_line if validated.end_line else total_lines
                lines = lines[start:end]
                content = "\n".join(lines)

            return ToolResult(
                tool_name=self.name,
                success=True,
                output=content,
                metadata={"file_path": clean_path, "total_lines": total_lines, "lines_returned": len(lines)},
            )
        except Exception as e:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(e))


# 3. write_file
class WriteFileInput(BaseModel):
    file_path: str = Field(description="Relative path of file to write/overwrite")
    content: str = Field(description="Complete text content to write into file")


class WriteFileOutput(BaseModel):
    file_path: str
    bytes_written: int


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Write or overwrite file content in the workspace"
    args_schema = WriteFileInput
    permission_required = ToolPermission.WRITE
    timeout_seconds = 30
    output_schema = WriteFileOutput

    async def execute(self, sandbox: SandboxInterface, sandbox_id: str, **kwargs) -> ToolResult:
        validated: WriteFileInput = self.validate_inputs(kwargs)  # type: ignore
        clean_path = PathValidator.validate_workspace_path(validated.file_path)

        try:
            await sandbox.write_file(sandbox_id, clean_path, validated.content)
            bytes_written = len(validated.content.encode("utf-8"))
            return ToolResult(
                tool_name=self.name,
                success=True,
                output=f"Successfully wrote {bytes_written} bytes to {clean_path}",
                metadata={"file_path": clean_path, "bytes_written": bytes_written},
            )
        except Exception as e:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(e))


# 4. create_file
class CreateFileInput(BaseModel):
    file_path: str = Field(description="Relative path of new file to create")
    initial_content: str = Field(default="", description="Initial content of the file")


class CreateFileOutput(BaseModel):
    file_path: str
    created: bool


class CreateFileTool(BaseTool):
    name = "create_file"
    description = "Create a new file in workspace if it does not already exist"
    args_schema = CreateFileInput
    permission_required = ToolPermission.WRITE
    timeout_seconds = 30
    output_schema = CreateFileOutput

    async def execute(self, sandbox: SandboxInterface, sandbox_id: str, **kwargs) -> ToolResult:
        validated: CreateFileInput = self.validate_inputs(kwargs)  # type: ignore
        clean_path = PathValidator.validate_workspace_path(validated.file_path)

        try:
            # Check if file exists
            exists_res = await sandbox.execute_command(sandbox_id, f"test -f '{clean_path}'", timeout_seconds=10)
            if exists_res.exit_code == 0:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    output="",
                    error=f"File '{clean_path}' already exists.",
                    metadata={"file_path": clean_path},
                )

            await sandbox.write_file(sandbox_id, clean_path, validated.initial_content)
            return ToolResult(
                tool_name=self.name,
                success=True,
                output=f"Created new file at '{clean_path}'",
                metadata={"file_path": clean_path, "created": True},
            )
        except Exception as e:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(e))


# 5. delete_file
class DeleteFileInput(BaseModel):
    file_path: str = Field(description="Relative path of file to delete")


class DeleteFileOutput(BaseModel):
    file_path: str
    deleted: bool


class DeleteFileTool(BaseTool):
    name = "delete_file"
    description = "Safely delete a specified file from the workspace"
    args_schema = DeleteFileInput
    permission_required = ToolPermission.WRITE
    timeout_seconds = 30
    output_schema = DeleteFileOutput

    async def execute(self, sandbox: SandboxInterface, sandbox_id: str, **kwargs) -> ToolResult:
        validated: DeleteFileInput = self.validate_inputs(kwargs)  # type: ignore
        clean_path = PathValidator.validate_workspace_path(validated.file_path)

        try:
            del_res = await sandbox.execute_command(sandbox_id, f"rm '{clean_path}'", timeout_seconds=15)
            success = del_res.exit_code == 0
            return ToolResult(
                tool_name=self.name,
                success=success,
                output=f"File '{clean_path}' deleted." if success else "",
                error=del_res.stderr if not success else None,
                metadata={"file_path": clean_path, "deleted": success},
            )
        except Exception as e:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(e))


# 6. search_files
class SearchFilesInput(BaseModel):
    query: str = Field(description="Text or pattern to search for across files")
    file_pattern: str = Field(default="*", description="Glob file pattern (e.g. *.py)")


class SearchFilesOutput(BaseModel):
    matches: List[Dict[str, Any]]
    count: int


class SearchFilesTool(BaseTool):
    name = "search_files"
    description = "Search for a text string or regex pattern across workspace files"
    args_schema = SearchFilesInput
    permission_required = ToolPermission.READ
    timeout_seconds = 30
    output_schema = SearchFilesOutput

    async def execute(self, sandbox: SandboxInterface, sandbox_id: str, **kwargs) -> ToolResult:
        validated: SearchFilesInput = self.validate_inputs(kwargs)  # type: ignore

        try:
            # Escape single quotes in query
            safe_query = validated.query.replace("'", "'\\''")
            cmd = f"grep -rn --include='{validated.file_pattern}' '{safe_query}' ."
            res = await sandbox.execute_command(sandbox_id, cmd, timeout_seconds=25)

            lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
            return ToolResult(
                tool_name=self.name,
                success=res.exit_code in (0, 1),  # exit code 1 means no match found cleanly
                output=res.stdout if res.exit_code == 0 else "No matches found.",
                error=res.stderr if res.exit_code not in (0, 1) else None,
                metadata={"matches_count": len(lines), "query": validated.query},
            )
        except Exception as e:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(e))


# 7. get_project_structure
class GetProjectStructureInput(BaseModel):
    max_depth: int = Field(default=4, ge=1, le=10, description="Maximum directory tree depth to display")


class GetProjectStructureOutput(BaseModel):
    structure: str


class GetProjectStructureTool(BaseTool):
    name = "get_project_structure"
    description = "Get directory tree structure of the workspace"
    args_schema = GetProjectStructureInput
    permission_required = ToolPermission.READ
    timeout_seconds = 20
    output_schema = GetProjectStructureOutput

    async def execute(self, sandbox: SandboxInterface, sandbox_id: str, **kwargs) -> ToolResult:
        validated: GetProjectStructureInput = self.validate_inputs(kwargs)  # type: ignore

        try:
            cmd = f"tree -L {validated.max_depth} -I '__pycache__|.git|node_modules|.venv|.pytest_cache'"
            res = await sandbox.execute_command(sandbox_id, cmd, timeout_seconds=15)
            if res.exit_code != 0:
                # Fallback to find command if tree is not available
                cmd = f"find . -maxdepth {validated.max_depth} -not -path '*/.*'"
                res = await sandbox.execute_command(sandbox_id, cmd, timeout_seconds=15)

            return ToolResult(
                tool_name=self.name,
                success=res.exit_code == 0,
                output=res.stdout,
                error=res.stderr if res.exit_code != 0 else None,
                metadata={"max_depth": validated.max_depth},
            )
        except Exception as e:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(e))
