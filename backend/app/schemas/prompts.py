from datetime import datetime, timezone
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


# --- Prompt Metadata & Audit Schemas ---

class PromptRole(str, Enum):
    REQUIREMENT_ANALYZER = "requirement_analyzer"
    PROJECT_ANALYZER = "project_analyzer"
    ANALYZER = "analyzer"
    PLANNER = "planner"
    CODER = "coder"
    DEBUGGER = "debugger"
    TESTER = "tester"
    REVIEWER = "reviewer"


class PromptMetadata(BaseModel):
    role: str
    version: str
    variant: str = "default"
    file_path: str
    content_hash: str
    description: Optional[str] = None


class PromptAuditRecord(BaseModel):
    audit_id: str
    run_id: str
    role: str
    version: str
    variant: str
    content_hash: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# --- 1. Requirement & Project Analyzer Schemas ---

class RequirementAnalyzerInput(BaseModel):
    requirement_prompt: str = Field(..., description="Raw requirement prompt from user")
    project_tree: str = Field(default="", description="Workspace file directory tree")


class RequirementAnalysisOutput(BaseModel):
    primary_goal: str = Field(..., description="Primary software goal")
    scope_summary: str = Field(..., description="Functional scope and boundaries")
    identified_components: List[str] = Field(default_factory=list, description="Identified components and files")
    technical_constraints: List[str] = Field(default_factory=list, description="Technical constraints")
    risk_assessment: str = Field(default="Low", description="Risk level and explanation")


class ProjectAnalyzerInput(BaseModel):
    project_root: str = Field(default=".", description="Root path of project")
    file_tree: str = Field(..., description="File directory tree")
    key_files_content: Optional[str] = Field(default=None, description="Content of key configuration files")


class ProjectAnalysisOutput(BaseModel):
    architecture_style: str = Field(default="Layered Architecture", description="Architecture style")
    frameworks_and_libraries: List[str] = Field(default_factory=list, description="Detected frameworks")
    entry_points: List[str] = Field(default_factory=list, description="Application entry points")
    key_modules: Dict[str, str] = Field(default_factory=dict, description="Module path mapping to responsibility")
    coding_conventions: List[str] = Field(default_factory=list, description="Detected coding conventions")


# --- 2. Planner Schemas ---

class PlannerInput(BaseModel):
    requirement: str = Field(..., description="Task requirement")
    analysis_summary: str = Field(..., description="Requirement and project analysis summary")
    file_tree: str = Field(default="", description="Workspace file tree")


class PlanStepSchema(BaseModel):
    step_number: int = Field(..., description="Step sequence index")
    description: str = Field(..., description="Description of changes in this step")
    target_files: List[str] = Field(default_factory=list, description="Target file paths")
    action_type: str = Field(default="modify", description="create, modify, or delete")
    verification_command: Optional[str] = Field(default=None, description="Test/command to run for verification")


class PlannerOutput(BaseModel):
    goals_summary: str = Field(..., description="Summary of implementation goals")
    steps: List[PlanStepSchema] = Field(default_factory=list, description="Ordered step-by-step implementation plan")
    plan_markdown: str = Field(..., description="Markdown representation of plan")


# --- 3. Coder Schemas ---

class CoderInput(BaseModel):
    requirement: str = Field(..., description="Requirement for code generation")
    file_path: str = Field(..., description="Target file path")
    language: str = Field(default="python", description="Source code language")
    plan_step: Optional[str] = Field(default=None, description="Implementation step description")
    existing_code: Optional[str] = Field(default=None, description="Existing content of file if modifying")


class CoderOutput(BaseModel):
    file_path: str = Field(..., description="Target file path")
    action: str = Field(default="modify", description="create, modify, or delete")
    reason: str = Field(..., description="Rationale for changes")
    code_content: str = Field(..., description="Complete updated source code")
    explanation: str = Field(default="", description="Summary of modifications")


# --- 4. Debugger Schemas ---

class DebuggerInput(BaseModel):
    requirement: str = Field(..., description="Requirement or user prompt")
    changed_files: List[str] = Field(default_factory=list, description="Modified file paths")
    test_results: Optional[str] = Field(default=None, description="Failed test output")
    error_logs: Optional[str] = Field(default=None, description="Stack traces and runtime error logs")


class DebuggerOutput(BaseModel):
    root_cause: str = Field(..., description="Detailed root cause explanation")
    affected_files: List[str] = Field(default_factory=list, description="Files affected by bug")
    proposed_fix: str = Field(..., description="Targeted repair strategy")
    confidence: float = Field(default=0.85, ge=0.0, le=1.0, description="Confidence score 0.0-1.0")


# --- 5. Tester Schemas ---

class TesterInput(BaseModel):
    __test__ = False
    framework: str = Field(default="pytest", description="Testing framework name")
    modified_files: List[str] = Field(default_factory=list, description="Modified file paths")
    exit_code: int = Field(default=0, description="Command exit code")
    raw_output: str = Field(default="", description="Raw stdout/stderr from test runner")


class FailingTestSchema(BaseModel):
    test_name: str = Field(..., description="Name of failing test")
    file_path: str = Field(..., description="Path to test file")
    line_number: Optional[int] = Field(default=None, description="Line number of failure")
    failure_message: str = Field(default="", description="Failure error message")


class TesterOutput(BaseModel):
    __test__ = False
    passed: bool = Field(..., description="True if all tests passed")
    total_tests: int = Field(default=0, ge=0)
    passed_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    skipped_count: int = Field(default=0, ge=0)
    failing_tests: List[FailingTestSchema] = Field(default_factory=list)
    likely_causes: List[str] = Field(default_factory=list)
    summary: str = Field(default="", description="Summary string")


# --- 6. Reviewer Schemas ---

class ReviewerInput(BaseModel):
    requirement: str = Field(default="", description="Task requirement")
    plan: Optional[str] = Field(default=None, description="Implementation plan")
    diff_summary: Optional[str] = Field(default=None, description="Git diff and status")
    modified_files: List[str] = Field(default_factory=list, description="Modified file paths")
    test_results: Optional[str] = Field(default=None, description="Test runner summary")


class ReviewFindingSchema(BaseModel):
    finding: str = Field(..., description="Short title of finding")
    severity: str = Field(..., description="CRITICAL, HIGH, MEDIUM, LOW, or INFO")
    affected_file: str = Field(..., description="Affected file path")
    explanation: str = Field(..., description="Detailed explanation")
    recommended_fix: str = Field(..., description="Recommended fix strategy")
    category: str = Field(default="code_quality", description="One of 12 review categories")


class ReviewerOutput(BaseModel):
    passed: bool = Field(..., description="True if review passes with no blocking issues")
    summary: str = Field(..., description="Overall review summary")
    findings: List[ReviewFindingSchema] = Field(default_factory=list, description="List of review findings")
