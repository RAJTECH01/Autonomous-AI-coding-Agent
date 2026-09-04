import { AgentLimits, AgentState, ExecutionMode } from './agent';

export interface CodingTaskCreateInput {
  project_id: string;
  requirement_prompt: string;
  language_runtime: string;
  execution_mode: ExecutionMode;
  auto_approve: boolean;
  limits: AgentLimits;
}

export interface CodingTask {
  id: string;
  project_id: string;
  project_name?: string;
  title: string;
  requirement_prompt: string;
  language_runtime: string;
  execution_mode: ExecutionMode;
  auto_approve: boolean;
  status: AgentState;
  created_at: string;
  completed_at?: string;
  last_run_id?: string;
  runs_count: number;
}
