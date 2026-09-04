import pytest
from app.infrastructure.db.models import (
    Base,
    UserModel,
    ProjectModel,
    CodingTaskModel,
    AgentRunModel,
    AgentStepModel,
    ToolCallModel,
    ToolResultModel,
    TokenUsageLogModel,
    ExecutionLogModel
)


def test_database_models_metadata_compilation():
    """Verify that all 20 domain models are registered with SQLAlchemy metadata without errors."""
    tables = Base.metadata.tables
    
    assert "users" in tables
    assert "auth_sessions" in tables
    assert "api_keys" in tables
    assert "provider_credentials" in tables
    assert "projects" in tables
    assert "project_members" in tables
    assert "project_files" in tables
    assert "coding_tasks" in tables
    assert "agent_runs" in tables
    assert "agent_plans" in tables
    assert "agent_steps" in tables
    assert "tool_calls" in tables
    assert "tool_results" in tables
    assert "code_versions" in tables
    assert "test_executions" in tables
    assert "error_logs" in tables
    assert "code_fixes" in tables
    assert "token_usage_logs" in tables
    assert "execution_logs" in tables
    assert "audit_logs" in tables

    # Verify key constraint expectations
    assert len(tables["users"].primary_key) == 1
    assert "email" in tables["users"].columns
    assert "refresh_token_hash" in tables["auth_sessions"].columns
