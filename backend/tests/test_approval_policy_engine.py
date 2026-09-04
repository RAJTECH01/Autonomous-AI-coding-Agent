import pytest
from app.core.approval.policy_engine import ApprovalPolicyEngine
from app.domain.entities.human_approval import HighRiskCategory


def test_policy_engine_detects_delete_many_files():
    engine = ApprovalPolicyEngine()
    
    # 2 files deleted
    plan_markdown = "Step 1: Delete old migration and auth helper."
    res = engine.evaluate_plan(plan_markdown, target_files=["old_migration.py", "auth_helper.py"], steps=[{"action_type": "delete"}])
    assert res.is_high_risk is True
    assert HighRiskCategory.DELETE_MANY_FILES in res.flagged_categories


def test_policy_engine_detects_auth_changes():
    engine = ApprovalPolicyEngine()
    
    res = engine.evaluate_plan("Modify JWT auth token payload", target_files=["backend/app/core/security.py"])
    assert res.is_high_risk is True
    assert HighRiskCategory.CHANGE_AUTH in res.flagged_categories


def test_policy_engine_detects_prod_config():
    engine = ApprovalPolicyEngine()
    
    res = engine.evaluate_plan("Update docker-compose environment", target_files=["docker-compose.yml"])
    assert res.is_high_risk is True
    assert HighRiskCategory.MODIFY_PROD_CONFIG in res.flagged_categories


def test_policy_engine_detects_db_schema_changes():
    engine = ApprovalPolicyEngine()
    
    res = engine.evaluate_plan("Add new Alembic migration for user table", target_files=["alembic/versions/001_initial.py"])
    assert res.is_high_risk is True
    assert HighRiskCategory.CHANGE_DB_SCHEMA in res.flagged_categories


def test_policy_engine_detects_dependency_installation():
    engine = ApprovalPolicyEngine()
    
    res = engine.evaluate_plan("Run pip install passlib", target_files=["requirements.txt"])
    assert res.is_high_risk is True
    assert HighRiskCategory.INSTALL_DEPENDENCIES in res.flagged_categories


def test_policy_engine_detects_network_access():
    engine = ApprovalPolicyEngine()
    
    res = engine.evaluate_plan("Execute curl request to external endpoint")
    assert res.is_high_risk is True
    assert HighRiskCategory.ENABLE_NETWORK_ACCESS in res.flagged_categories


def test_policy_engine_detects_privileged_operations():
    engine = ApprovalPolicyEngine()
    
    res = engine.evaluate_plan("Run sudo chmod +x script.sh")
    assert res.is_high_risk is True
    assert HighRiskCategory.EXECUTE_PRIVILEGED_OP in res.flagged_categories


def test_policy_engine_tool_call_evaluation():
    engine = ApprovalPolicyEngine()
    
    # Safe tool call
    safe_res = engine.evaluate_tool_call("read_file", {"file_path": "app/main.py"})
    assert safe_res.is_high_risk is False

    # High risk tool call: auth file modification
    auth_res = engine.evaluate_tool_call("write_file", {"file_path": "app/services/auth.py", "content": "def auth(): pass"})
    assert auth_res.is_high_risk is True
    assert HighRiskCategory.CHANGE_AUTH in auth_res.flagged_categories
