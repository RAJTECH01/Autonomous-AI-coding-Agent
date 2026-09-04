export interface TaskMetrics {
  started: number;
  completed: number;
  failed: number;
  average_execution_time_seconds: number;
  average_iterations: number;
}

export interface ToolBreakdown {
  [toolName: string]: {
    total: number;
    success: number;
    failed: number;
  };
}

export interface ToolMetrics {
  total_calls: number;
  breakdown: ToolBreakdown;
  test_failures: number;
  retry_count: number;
}

export interface AITelemetry {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  model_latencies_seconds: { [model: string]: number };
}

export interface InfrastructureMetrics {
  sandbox_failures: { [reason: string]: number };
  total_sandbox_failures: number;
}

export interface DashboardMetricsSummary {
  system_uptime_seconds: number;
  tasks: TaskMetrics;
  tools: ToolMetrics;
  ai_telemetry: AITelemetry;
  infrastructure: InfrastructureMetrics;
}

export interface BackgroundJob {
  job_id: string;
  name: string;
  job_type: string;
  status: string;
  start_time: string;
  end_time?: string;
  duration_seconds: number;
  command: string;
  exit_code?: number;
  last_log_snippet?: string;
}
