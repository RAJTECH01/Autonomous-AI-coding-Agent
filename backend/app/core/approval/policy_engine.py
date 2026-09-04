import re
from typing import List, Dict, Any, Optional
from app.domain.entities.human_approval import HighRiskCategory, HighRiskEvaluationResult


class ApprovalPolicyEngine:
    """
    Approval Policy Engine evaluating proposed plans, steps, target files, and tool calls
    against high-risk patterns to enforce mandatory human approval policies.
    """

    AUTH_KEYWORDS = [
        "auth", "security", "jwt", "passlib", "oauth", "password", "argon2",
        "permission", "access_token", "secret_key", "credential"
    ]

    PROD_CONFIG_FILES = [
        "docker-compose.yml", "docker-compose.yaml", "dockerfile", ".env",
        "nginx.conf", "settings.py", "config.py", "prod.env"
    ]

    DB_SCHEMA_KEYWORDS = [
        "alembic", "migration", "models.py", "schema.sql", "alter table",
        "drop table", "create table", "foreign key"
    ]

    DEPENDENCY_COMMANDS = [
        "pip install", "npm install", "npm i", "yarn add", "cargo add",
        "go get", "poetry add", "pipenv install"
    ]

    DEPENDENCY_FILES = [
        "requirements.txt", "package.json", "pyproject.toml", "cargo.toml", "go.mod"
    ]

    NETWORK_KEYWORDS = [
        "curl ", "wget ", "http://", "https://", "nc -l", "ncat", "socat"
    ]

    PRIVILEGED_OPS = [
        "sudo ", "chmod ", "chown ", "rm -rf", "systemctl ", "service ",
        "docker run", "docker exec", "eval("
    ]

    def evaluate_plan(
        self,
        plan_markdown: str,
        target_files: Optional[List[str]] = None,
        steps: Optional[List[Dict[str, Any]]] = None,
    ) -> HighRiskEvaluationResult:
        """Scan implementation plan markdown, target files, and steps for high-risk operations."""
        result = HighRiskEvaluationResult()
        files = target_files or []
        step_list = steps or []
        plan_text_lower = plan_markdown.lower()

        # 1. Delete many files / critical paths
        deleted_files = [f for f in files if "delete" in f.lower() or "remove" in f.lower()]
        for step in step_list:
            if step.get("action_type") in ["delete", "remove"]:
                deleted_files.extend(step.get("target_files", files))

        if "delete" in plan_text_lower or "remove" in plan_text_lower:
            deleted_files.extend(files)

        deleted_files = list(set(deleted_files))
        if len(deleted_files) >= 2 or "delete multiple files" in plan_text_lower or "rm -rf" in plan_text_lower:
            result.is_high_risk = True
            result.flagged_categories.append(HighRiskCategory.DELETE_MANY_FILES)
            result.explanations.append(f"Plan involves deleting files: {deleted_files}")

        # 2. Change Authentication & Security
        auth_files = [f for f in files if any(kw in f.lower() for kw in self.AUTH_KEYWORDS)]
        if auth_files or any(kw in plan_text_lower for kw in ["authentication", "jwt token", "password hashing", "security policy"]):
            result.is_high_risk = True
            result.flagged_categories.append(HighRiskCategory.CHANGE_AUTH)
            result.explanations.append(f"Plan modifies security/auth components: {auth_files or 'Auth keywords detected'}")

        # 3. Modify Production Configuration
        prod_files = [f for f in files if any(pcf in f.lower() for pcf in self.PROD_CONFIG_FILES)]
        if prod_files or any(pcf in plan_text_lower for pcf in self.PROD_CONFIG_FILES):
            result.is_high_risk = True
            result.flagged_categories.append(HighRiskCategory.MODIFY_PROD_CONFIG)
            result.explanations.append(f"Plan modifies production deployment configuration: {prod_files or 'Prod config detected'}")

        # 4. Change Database Schema
        db_files = [f for f in files if any(dbkw in f.lower() for dbkw in self.DB_SCHEMA_KEYWORDS)]
        if db_files or any(dbkw in plan_text_lower for dbkw in ["alembic migration", "schema migration", "alter table"]):
            result.is_high_risk = True
            result.flagged_categories.append(HighRiskCategory.CHANGE_DB_SCHEMA)
            result.explanations.append(f"Plan involves database schema or migration changes: {db_files or 'DB schema keywords detected'}")

        # 5. Install Dependencies
        dep_files = [f for f in files if any(df in f.lower() for df in self.DEPENDENCY_FILES)]
        if dep_files or any(cmd in plan_text_lower for cmd in self.DEPENDENCY_COMMANDS):
            result.is_high_risk = True
            result.flagged_categories.append(HighRiskCategory.INSTALL_DEPENDENCIES)
            result.explanations.append(f"Plan adds external package dependencies: {dep_files or 'Dependency installation detected'}")

        # 6. Enable Network Access
        if any(netkw in plan_text_lower for netkw in self.NETWORK_KEYWORDS):
            result.is_high_risk = True
            result.flagged_categories.append(HighRiskCategory.ENABLE_NETWORK_ACCESS)
            result.explanations.append("Plan involves outbound/inbound network socket access.")

        # 7. Execute Privileged Operations
        if any(priv in plan_text_lower for priv in self.PRIVILEGED_OPS):
            result.is_high_risk = True
            result.flagged_categories.append(HighRiskCategory.EXECUTE_PRIVILEGED_OP)
            result.explanations.append("Plan includes privileged operating system commands.")

        result.flagged_files = files
        return result

    def evaluate_tool_call(self, tool_name: str, tool_args: Dict[str, Any]) -> HighRiskEvaluationResult:
        """Scan an individual proposed tool call before execution."""
        result = HighRiskEvaluationResult()

        command = tool_args.get("command", "") or tool_args.get("cmd", "") or ""
        file_path = tool_args.get("file_path", "") or tool_args.get("target_file", "") or tool_args.get("AbsolutePath", "") or ""

        # Check command string
        cmd_lower = command.lower()
        path_lower = file_path.lower()

        # Check deletion
        if tool_name in ["delete_file", "remove_file"] or "rm " in cmd_lower:
            result.is_high_risk = True
            result.flagged_categories.append(HighRiskCategory.DELETE_MANY_FILES)
            result.explanations.append(f"Tool call attempts file deletion: {file_path or command}")

        # Check auth modification
        if any(kw in path_lower for kw in self.AUTH_KEYWORDS):
            result.is_high_risk = True
            result.flagged_categories.append(HighRiskCategory.CHANGE_AUTH)
            result.explanations.append(f"Tool call modifies security/auth file: {file_path}")

        # Check prod config
        if any(pcf in path_lower for pcf in self.PROD_CONFIG_FILES):
            result.is_high_risk = True
            result.flagged_categories.append(HighRiskCategory.MODIFY_PROD_CONFIG)
            result.explanations.append(f"Tool call modifies production config: {file_path}")

        # Check DB schema
        if any(dbkw in path_lower for dbkw in self.DB_SCHEMA_KEYWORDS) or "alembic" in cmd_lower:
            result.is_high_risk = True
            result.flagged_categories.append(HighRiskCategory.CHANGE_DB_SCHEMA)
            result.explanations.append(f"Tool call modifies database schema/migration: {file_path or command}")

        # Check dependency installation
        if any(depcmd in cmd_lower for depcmd in self.DEPENDENCY_COMMANDS) or any(df in path_lower for df in self.DEPENDENCY_FILES):
            result.is_high_risk = True
            result.flagged_categories.append(HighRiskCategory.INSTALL_DEPENDENCIES)
            result.explanations.append(f"Tool call installs external package dependencies: {command or file_path}")

        # Check network access
        if any(netkw in cmd_lower for netkw in self.NETWORK_KEYWORDS):
            result.is_high_risk = True
            result.flagged_categories.append(HighRiskCategory.ENABLE_NETWORK_ACCESS)
            result.explanations.append(f"Tool call executes network request: {command}")

        # Check privileged operation
        if any(priv in cmd_lower for priv in self.PRIVILEGED_OPS):
            result.is_high_risk = True
            result.flagged_categories.append(HighRiskCategory.EXECUTE_PRIVILEGED_OP)
            result.explanations.append(f"Tool call executes privileged OS operation: {command}")

        if path_lower:
            result.flagged_files.append(file_path)
        if cmd_lower:
            result.flagged_commands.append(command)

        return result
