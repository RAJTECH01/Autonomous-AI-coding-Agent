export type AgentState =
  | 'RECEIVED'
  | 'ANALYZING'
  | 'PLANNING'
  | 'AWAITING_APPROVAL'
  | 'IMPLEMENTING'
  | 'TESTING'
  | 'DEBUGGING'
  | 'REVIEWING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export interface AgentLimits {
  max_iterations: number;
  max_execution_time: number; // seconds
  max_tool_calls: number;
  max_files_changed: number;
  max_generated_output: number;
  max_test_attempts: number;
  max_review_attempts: number;
}

export interface ToolCallItem {
  id: string;
  tool_name: string;
  tool_input: Record<string, any>;
  status: 'pending' | 'executing' | 'success' | 'failed';
  execution_duration_ms?: number;
  output?: string;
  error?: string;
  created_at?: string;
}

export interface PlanStepItem {
  step_number: number;
  description: string;
  target_files: string[];
  action_type: 'create' | 'modify' | 'delete';
  verification_command?: string;
}

export interface AgentPlanData {
  id: string;
  goals_summary: string;
  plan_markdown: string;
  steps: PlanStepItem[];
  version: number;
  status: 'active' | 'approved' | 'superseded';
}

export interface FailingTestDetail {
  test_name: string;
  file_path: string;
  line_number?: number;
  failure_message: string;
  likely_cause?: string;
  stack_trace?: string;
}

export interface TestResultsData {
  framework: string;
  language: string;
  passed: boolean;
  total_tests: number;
  passed_count: number;
  failed_count: number;
  skipped_count: number;
  duration_ms: number;
  failing_tests: FailingTestDetail[];
  likely_causes: string[];
  summary: string;
}

export type ReviewSeverity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO';

export interface ReviewFindingItem {
  finding: string;
  severity: ReviewSeverity;
  affected_file: string;
  explanation: string;
  recommended_fix: string;
  category: string;
}

export interface ReviewResultData {
  passed: boolean;
  summary: string;
  findings: ReviewFindingItem[];
  blocking_findings_count: number;
  requires_another_cycle: boolean;
  timestamp: string;
}

export interface AgentExecutionStep {
  id: string;
  step_number: number;
  from_state: AgentState;
  to_state: AgentState;
  step_type: string;
  thought_process: Record<string, any>;
  tool_calls: ToolCallItem[];
  created_at: string;
}

export type ExecutionMode = 'PLAN_ONLY' | 'APPROVAL_REQUIRED' | 'AUTONOMOUS';

export interface AgentExecutionState {
  run_id: string;
  task_id: string;
  project_id: string;
  status: AgentState;
  execution_mode: ExecutionMode;
  high_risk_flagged: boolean;
  high_risk_triggers: string[];
  user_prompt: string;
  language_runtime: string;
  auto_approve: boolean;
  limits: AgentLimits;
  current_iteration: number;
  elapsed_seconds: number;
  active_plan?: AgentPlanData;
  inspected_files: string[];
  modified_files: string[];
  tool_calls: ToolCallItem[];
  latest_test_results?: TestResultsData;
  latest_error?: {
    error_type: string;
    stack_trace: string;
    root_cause?: string;
  };
  latest_fix?: {
    proposed_fix: string;
    affected_files: string[];
    diff_summary?: string;
  };
  final_review?: ReviewResultData;
  steps_history: AgentExecutionStep[];
  started_at?: string;
  completed_at?: string;
  logs: string[];
}
