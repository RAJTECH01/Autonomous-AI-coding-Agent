import os
import json
import re
import hashlib
import uuid
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type, Union
from pydantic import BaseModel

from app.schemas.prompts import (
    PromptRole,
    PromptMetadata,
    PromptAuditRecord,
    RequirementAnalyzerInput,
    RequirementAnalysisOutput,
    ProjectAnalyzerInput,
    ProjectAnalysisOutput,
    PlannerInput,
    PlannerOutput,
    CoderInput,
    CoderOutput,
    DebuggerInput,
    DebuggerOutput,
    TesterInput,
    TesterOutput,
    ReviewerInput,
    ReviewerOutput,
)
from app.core.logging import logger

ROLE_INPUT_SCHEMAS: Dict[str, Type[BaseModel]] = {
    PromptRole.REQUIREMENT_ANALYZER.value: RequirementAnalyzerInput,
    PromptRole.PROJECT_ANALYZER.value: ProjectAnalyzerInput,
    PromptRole.ANALYZER.value: RequirementAnalyzerInput,
    PromptRole.PLANNER.value: PlannerInput,
    PromptRole.CODER.value: CoderInput,
    PromptRole.DEBUGGER.value: DebuggerInput,
    PromptRole.TESTER.value: TesterInput,
    PromptRole.REVIEWER.value: ReviewerInput,
}

ROLE_OUTPUT_SCHEMAS: Dict[str, Type[BaseModel]] = {
    PromptRole.REQUIREMENT_ANALYZER.value: RequirementAnalysisOutput,
    PromptRole.PROJECT_ANALYZER.value: ProjectAnalysisOutput,
    PromptRole.ANALYZER.value: RequirementAnalysisOutput,
    PromptRole.PLANNER.value: PlannerOutput,
    PromptRole.CODER.value: CoderOutput,
    PromptRole.DEBUGGER.value: DebuggerOutput,
    PromptRole.TESTER.value: TesterOutput,
    PromptRole.REVIEWER.value: ReviewerOutput,
}


class PromptManager:
    """
    Versioned Prompt Management System.
    Loads prompt templates from external files under prompts/, supports versioning,
    A/B testing, Pydantic input/output schema validation, and audit tracking.
    """

    def __init__(self, prompts_dir: Optional[str] = None):
        self.prompts_dir = self._resolve_prompts_dir(prompts_dir)
        self.manifest = self._load_manifest()
        self.audit_records: List[PromptAuditRecord] = []

    def _resolve_prompts_dir(self, custom_path: Optional[str] = None) -> Path:
        """Resolve prompt template directory search path."""
        candidates = []
        if custom_path:
            candidates.append(Path(custom_path))

        # Check workspace root /prompts and backend/prompts
        cwd = Path.cwd()
        candidates.extend([
            cwd / "prompts",
            cwd / "backend" / "prompts",
            cwd.parent / "prompts",
            Path(__file__).resolve().parent.parent.parent.parent / "prompts",
            Path(__file__).resolve().parent.parent.parent / "prompts",
        ])

        for path in candidates:
            if path.exists() and path.is_dir():
                return path

        # Fallback to current working dir prompts
        default_path = cwd / "prompts"
        default_path.mkdir(parents=True, exist_ok=True)
        return default_path

    def _load_manifest(self) -> Dict[str, Any]:
        """Load manifest.json from prompt directory."""
        manifest_path = self.prompts_dir / "manifest.json"
        if manifest_path.exists():
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not parse prompt manifest at {manifest_path}", error=str(e))

        return {
            "default_version": "1.0.0",
            "roles": {},
            "ab_testing": {"enabled": False},
        }

    def resolve_variant(self, role: str, variant: Optional[str] = None, user_or_task_id: Optional[str] = None) -> str:
        """
        Resolve prompt variant supporting A/B testing.
        If variant is specified, returns it.
        Otherwise, if A/B testing is enabled for the role, deterministically allocates variant.
        """
        if variant:
            return variant

        ab_config = self.manifest.get("ab_testing", {})
        if ab_config.get("enabled"):
            role_allocations = ab_config.get("allocations", {}).get(role)
            if role_allocations and user_or_task_id:
                # Deterministic hash allocation for A/B testing
                hash_val = int(hashlib.sha256(f"{role}:{user_or_task_id}".encode()).hexdigest(), 16)
                roll = (hash_val % 100) / 100.0
                cumulative = 0.0
                for var_name, weight in role_allocations.items():
                    cumulative += weight
                    if roll <= cumulative:
                        return var_name

        return "default"

    def get_prompt_metadata(
        self,
        role: str,
        variant: Optional[str] = None,
        user_or_task_id: Optional[str] = None,
    ) -> PromptMetadata:
        """Fetch metadata for a given role and variant."""
        role_str = role.value if isinstance(role, Enum) else str(role)
        resolved_variant = self.resolve_variant(role_str, variant=variant, user_or_task_id=user_or_task_id)

        role_info = self.manifest.get("roles", {}).get(role_str, {})
        version = role_info.get("variants", {}).get(resolved_variant, role_info.get("active_version", "1.0.0"))

        # Determine template file path
        if resolved_variant != "default" and role_info.get("variants", {}).get(resolved_variant):
            file_name = f"{role_str}_{resolved_variant}.txt"
        else:
            file_name = role_info.get("file", f"{role_str}.txt")
            if "/" in file_name:
                file_name = Path(file_name).name

        template_file = self.prompts_dir / file_name
        if not template_file.exists():
            # Fall back to role_str.txt
            template_file = self.prompts_dir / f"{role_str}.txt"

        content = ""
        content_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        if template_file.exists():
            try:
                content = template_file.read_text(encoding="utf-8")
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            except Exception as e:
                logger.warning(f"Error reading prompt template file '{template_file}'", error=str(e))

        return PromptMetadata(
            role=role_str,
            version=version,
            variant=resolved_variant,
            file_path=str(template_file),
            content_hash=content_hash,
            description=f"Prompt for {role_str} (v{version}, variant {resolved_variant})",
        )

    def load_raw_template(self, role: str, variant: Optional[str] = None) -> str:
        """Load raw template text from prompts directory."""
        metadata = self.get_prompt_metadata(role=role, variant=variant)
        file_path = Path(metadata.file_path)
        if file_path.exists():
            return file_path.read_text(encoding="utf-8")
        raise FileNotFoundError(f"Prompt template file not found at: {file_path}")

    def render_prompt(
        self,
        role: Union[str, PromptRole],
        inputs: Union[BaseModel, Dict[str, Any]],
        variant: Optional[str] = None,
        user_or_task_id: Optional[str] = None,
    ) -> Tuple[str, PromptMetadata]:
        """
        Validate inputs against Pydantic schema and render template text.
        Returns (rendered_prompt_string, PromptMetadata).
        """
        role_str = role.value if isinstance(role, PromptRole) else str(role)
        schema_cls = ROLE_INPUT_SCHEMAS.get(role_str)

        # Validate inputs with Pydantic model
        if schema_cls:
            if isinstance(inputs, dict):
                validated_inputs = schema_cls(**inputs)
            elif isinstance(inputs, schema_cls):
                validated_inputs = inputs
            else:
                validated_inputs = schema_cls(**inputs.model_dump() if hasattr(inputs, "model_dump") else inputs.dict())
            input_dict = validated_inputs.model_dump() if hasattr(validated_inputs, "model_dump") else validated_inputs.dict()
        else:
            input_dict = inputs.model_dump() if isinstance(inputs, BaseModel) else dict(inputs)

        metadata = self.get_prompt_metadata(role=role_str, variant=variant, user_or_task_id=user_or_task_id)
        raw_template = self.load_raw_template(role=role_str, variant=metadata.variant)

        # Format template with input dict
        try:
            rendered = raw_template.format(**input_dict)
        except KeyError as ke:
            # Fallback formatting if missing keys or unescaped braces
            logger.warning(f"KeyError while formatting template '{role_str}': {ke}. Performing key replacement.")
            rendered = raw_template
            for k, v in input_dict.items():
                rendered = rendered.replace(f"{{{k}}}", str(v))

        return rendered, metadata

    def parse_and_validate_output(
        self,
        role: Union[str, PromptRole],
        llm_response_content: str,
    ) -> BaseModel:
        """
        Parse LLM output JSON string and validate against corresponding Pydantic output schema.
        """
        role_str = role.value if isinstance(role, PromptRole) else str(role)
        schema_cls = ROLE_OUTPUT_SCHEMAS.get(role_str)

        if not schema_cls:
            raise ValueError(f"No Pydantic output schema registered for role '{role_str}'")

        content = llm_response_content.strip()
        json_str = content

        # Clean markdown code blocks if present
        if "```" in content:
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if match:
                json_str = match.group(1)
            else:
                start = content.find("{")
                end = content.rfind("}")
                if start != -1 and end != -1:
                    json_str = content[start:end+1]

        data = json.loads(json_str)
        return schema_cls(**data)

    def audit_prompt_execution(
        self,
        run_id: str,
        metadata: PromptMetadata,
    ) -> PromptAuditRecord:
        """Create and store audit record for a prompt execution."""
        audit = PromptAuditRecord(
            audit_id=str(uuid.uuid4()),
            run_id=run_id,
            role=metadata.role,
            version=metadata.version,
            variant=metadata.variant,
            content_hash=metadata.content_hash,
        )
        self.audit_records.append(audit)
        return audit


# Global singleton instance
_prompt_manager_instance: Optional[PromptManager] = None


def get_prompt_manager(prompts_dir: Optional[str] = None) -> PromptManager:
    global _prompt_manager_instance
    if _prompt_manager_instance is None or prompts_dir is not None:
        _prompt_manager_instance = PromptManager(prompts_dir=prompts_dir)
    return _prompt_manager_instance
