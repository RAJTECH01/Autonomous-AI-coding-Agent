import json
import pytest
from pathlib import Path
from app.core.prompts.manager import PromptManager, get_prompt_manager
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


def test_prompt_manager_template_loading():
    """Verify PromptManager loads all required template files from prompts/ directory."""
    pm = get_prompt_manager()

    roles = [
        PromptRole.REQUIREMENT_ANALYZER,
        PromptRole.PROJECT_ANALYZER,
        PromptRole.ANALYZER,
        PromptRole.PLANNER,
        PromptRole.CODER,
        PromptRole.DEBUGGER,
        PromptRole.TESTER,
        PromptRole.REVIEWER,
    ]

    for role in roles:
        meta = pm.get_prompt_metadata(role)
        assert meta.role == role.value
        assert meta.version == "1.0.0"
        assert meta.content_hash is not None
        assert len(meta.content_hash) == 64  # Valid SHA-256 hash length

        template_text = pm.load_raw_template(role)
        assert len(template_text) > 0


def test_prompt_rendering_with_pydantic_inputs():
    """Verify rendering prompt templates using Pydantic input models."""
    pm = get_prompt_manager()

    # 1. Requirement Analyzer
    req_input = RequirementAnalyzerInput(
        requirement_prompt="Build user auth API",
        project_tree="backend/\n  app/",
    )
    rendered, meta = pm.render_prompt(PromptRole.REQUIREMENT_ANALYZER, req_input)
    assert "Build user auth API" in rendered
    assert "backend/" in rendered

    # 2. Planner
    planner_input = PlannerInput(
        requirement="Add payments endpoint",
        analysis_summary="Need Stripe integration",
        file_tree="app/services/",
    )
    rendered, meta = pm.render_prompt(PromptRole.PLANNER, planner_input)
    assert "Add payments endpoint" in rendered
    assert "Stripe integration" in rendered

    # 3. Coder
    coder_input = CoderInput(
        requirement="Create user entity",
        file_path="app/domain/entities/user.py",
        language="python",
        plan_step="Step 1 create file",
        existing_code="# Empty file",
    )
    rendered, meta = pm.render_prompt(PromptRole.CODER, coder_input)
    assert "app/domain/entities/user.py" in rendered
    assert "# Empty file" in rendered


def test_structured_output_parsing_and_pydantic_validation():
    """Verify parsing LLM responses into validated Pydantic models for each role."""
    pm = get_prompt_manager()

    # 1. Requirement Analyzer Output
    raw_req_output = json.dumps({
        "primary_goal": "Build JWT Authentication Service",
        "scope_summary": "Endpoints for register, login, refresh token",
        "identified_components": ["app/api/v1/auth.py", "app/core/security.py"],
        "technical_constraints": ["Argon2 hashing required"],
        "risk_assessment": "Low risk with standard OAuth2"
    })
    parsed_req = pm.parse_and_validate_output(PromptRole.REQUIREMENT_ANALYZER, raw_req_output)
    assert isinstance(parsed_req, RequirementAnalysisOutput)
    assert parsed_req.primary_goal == "Build JWT Authentication Service"

    # 2. Planner Output
    raw_planner_output = json.dumps({
        "goals_summary": "Implement auth endpoints",
        "steps": [
            {
                "step_number": 1,
                "description": "Create auth schema",
                "target_files": ["app/schemas/auth.py"],
                "action_type": "create",
                "verification_command": "pytest tests/test_auth.py"
            }
        ],
        "plan_markdown": "# Implementation Plan\n\n1. Create auth schema"
    })
    parsed_planner = pm.parse_and_validate_output(PromptRole.PLANNER, raw_planner_output)
    assert isinstance(parsed_planner, PlannerOutput)
    assert len(parsed_planner.steps) == 1
    assert parsed_planner.steps[0].target_files == ["app/schemas/auth.py"]

    # 3. Debugger Output
    raw_debug_output = json.dumps({
        "root_cause": "Missing Authorization header in request context",
        "affected_files": ["app/api/middlewares/auth.py"],
        "proposed_fix": "Extract bearer token from headers dict safely",
        "confidence": 0.92
    })
    parsed_debug = pm.parse_and_validate_output(PromptRole.DEBUGGER, raw_debug_output)
    assert isinstance(parsed_debug, DebuggerOutput)
    assert parsed_debug.confidence == 0.92

    # 4. Reviewer Output
    raw_review_output = json.dumps({
        "passed": False,
        "summary": "Security risk detected",
        "findings": [
            {
                "finding": "Insecure CORS configuration",
                "severity": "HIGH",
                "affected_file": "app/main.py",
                "explanation": "Allow origins set to wildcard *",
                "recommended_fix": "Restrict origins to whitelist",
                "category": "security"
            }
        ]
    })
    parsed_review = pm.parse_and_validate_output(PromptRole.REVIEWER, raw_review_output)
    assert isinstance(parsed_review, ReviewerOutput)
    assert parsed_review.passed is False
    assert parsed_review.findings[0].severity == "HIGH"


def test_ab_testing_variant_resolution():
    """Verify A/B testing variant resolution and deterministic hash allocation."""
    pm = get_prompt_manager()

    # Default variant
    var_default = pm.resolve_variant("planner", variant=None, user_or_task_id=None)
    assert var_default in ["default", "variant_a", "variant_b"]

    # Explicit variant override
    var_override = pm.resolve_variant("planner", variant="variant_b")
    assert var_override == "variant_b"

    # Deterministic task_id hashing
    var_1 = pm.resolve_variant("planner", user_or_task_id="task_abc_123")
    var_2 = pm.resolve_variant("planner", user_or_task_id="task_abc_123")
    assert var_1 == var_2  # Must be deterministic for same task ID


def test_prompt_audit_logging():
    """Verify recording of prompt execution audit records."""
    pm = get_prompt_manager()
    meta = pm.get_prompt_metadata(PromptRole.PLANNER)

    audit_rec = pm.audit_prompt_execution(run_id="run_test_777", metadata=meta)
    assert isinstance(audit_rec, PromptAuditRecord)
    assert audit_rec.run_id == "run_test_777"
    assert audit_rec.role == PromptRole.PLANNER.value
    assert audit_rec.version == "1.0.0"
    assert audit_rec.content_hash == meta.content_hash
    assert len(pm.audit_records) >= 1
