import { create } from 'zustand';
import { AgentExecutionState, AgentState, AgentLimits, ExecutionMode } from '../types/agent';
import { CodingTask } from '../types/task';

interface AgentExecutionStoreState {
  tasks: CodingTask[];
  activeExecution: AgentExecutionState | null;
  isLoading: boolean;
  error: string | null;

  // Actions
  startNewTask: (input: {
    projectId: string;
    requirementPrompt: string;
    languageRuntime: string;
    executionMode: ExecutionMode;
    autoApprove: boolean;
    limits: AgentLimits;
  }) => string; // returns runId / taskId
  approvePlan: (runId: string) => void;
  rejectPlan: (runId: string, feedbackNotes?: string) => void;
  cancelExecution: (runId: string) => void;
  modifyRequirements: (runId: string, updatedPrompt: string) => void;
  retryTask: (taskId: string) => void;
  setActiveExecutionByRunId: (runId: string) => void;
}

const INITIAL_LIMITS: AgentLimits = {
  max_iterations: 20,
  max_execution_time: 300,
  max_tool_calls: 50,
  max_files_changed: 20,
  max_generated_output: 100000,
  max_test_attempts: 5,
  max_review_attempts: 3,
};

const DEFAULT_TASKS: CodingTask[] = [
  {
    id: 'task-101',
    project_id: 'proj-auth-service',
    project_name: 'Authentication Microservice',
    title: 'Implement JWT refresh token endpoint with Argon2 hashing',
    requirement_prompt: 'Create POST /api/v1/auth/refresh endpoint supporting refresh token rotation and revocation list.',
    language_runtime: 'Python (3.11)',
    execution_mode: 'AUTONOMOUS',
    auto_approve: true,
    status: 'COMPLETED',
    created_at: new Date(Date.now() - 3600000).toISOString(),
    completed_at: new Date(Date.now() - 3300000).toISOString(),
    last_run_id: 'run-881',
    runs_count: 1,
  },
  {
    id: 'task-102',
    project_id: 'proj-agent-core',
    project_name: 'Autonomous Agent Engine',
    title: 'Implement versioned prompt management system with Pydantic validation',
    requirement_prompt: 'Decouple prompts into external prompts/ files, support versioning, A/B testing, and audit logging.',
    language_runtime: 'Python (3.11)',
    execution_mode: 'APPROVAL_REQUIRED',
    auto_approve: false,
    status: 'AWAITING_APPROVAL',
    created_at: new Date(Date.now() - 1200000).toISOString(),
    last_run_id: 'run-992',
    runs_count: 1,
  },
  {
    id: 'task-103',
    project_id: 'proj-react-frontend',
    project_name: 'Web Management Console',
    title: 'Build production React + TypeScript agent monitoring workspace',
    requirement_prompt: 'Implement 11 pages displaying agent state, plan, tool calls, test results, and final code reviews.',
    language_runtime: 'TypeScript (React)',
    execution_mode: 'AUTONOMOUS',
    auto_approve: true,
    status: 'IMPLEMENTING',
    created_at: new Date(Date.now() - 300000).toISOString(),
    last_run_id: 'run-993',
    runs_count: 1,
  },
];

const DEFAULT_EXECUTIONS: Record<string, AgentExecutionState> = {
  'run-993': {
    run_id: 'run-993',
    task_id: 'task-103',
    project_id: 'proj-react-frontend',
    status: 'IMPLEMENTING',
    execution_mode: 'AUTONOMOUS',
    high_risk_flagged: false,
    high_risk_triggers: [],
    user_prompt: 'Build production React + TypeScript agent monitoring workspace displaying agent state, plan, inspected files, tool calls, test results, and final code reviews.',
    language_runtime: 'TypeScript (React)',
    auto_approve: true,
    limits: INITIAL_LIMITS,
    current_iteration: 4,
    elapsed_seconds: 48,
    inspected_files: [
      'frontend/src/App.tsx',
      'frontend/src/index.css',
      'frontend/package.json',
      'frontend/src/types/agent.ts',
    ],
    modified_files: [
      'frontend/src/types/agent.ts',
      'frontend/src/types/project.ts',
      'frontend/src/store/useNavigationStore.ts',
      'frontend/src/pages/AgentExecutionPage.tsx',
    ],
    active_plan: {
      id: 'plan-103',
      goals_summary: 'Build responsive 11-page React + TypeScript frontend with live execution monitoring.',
      plan_markdown: `# React Frontend Implementation Plan\n\n1. Define TypeScript types in \`frontend/src/types/\`.\n2. Build Zustand stores for navigation and state.\n3. Build modular UI components for logs, tool calls, plans, and test results.\n4. Create all 11 required pages.\n5. Wire navigation bar and full layout.`,
      steps: [
        { step_number: 1, description: 'Define TypeScript types for agent execution', target_files: ['frontend/src/types/agent.ts'], action_type: 'create' },
        { step_number: 2, description: 'Build Zustand stores for page navigation & execution state', target_files: ['frontend/src/store/useNavigationStore.ts'], action_type: 'create' },
        { step_number: 3, description: 'Implement AgentExecutionPage with live step viewer', target_files: ['frontend/src/pages/AgentExecutionPage.tsx'], action_type: 'create' },
        { step_number: 4, description: 'Execute Vitest suite verification', target_files: ['frontend/tests/App.test.tsx'], action_type: 'modify', verification_command: 'npm run test' },
      ],
      version: 1,
      status: 'approved',
    },
    tool_calls: [
      { id: 'tc-1', tool_name: 'list_dir', tool_input: { DirectoryPath: 'frontend/src' }, status: 'success', execution_duration_ms: 12, output: 'App.tsx, main.tsx, index.css' },
      { id: 'tc-2', tool_name: 'read_file', tool_input: { AbsolutePath: 'frontend/package.json' }, status: 'success', execution_duration_ms: 8, output: '{"name": "autonomous-coding-agent-frontend"}' },
      { id: 'tc-3', tool_name: 'write_file', tool_input: { TargetFile: 'frontend/src/types/agent.ts' }, status: 'success', execution_duration_ms: 25, output: 'File created successfully.' },
      { id: 'tc-4', tool_name: 'run_tests', tool_input: { command: 'npm run test' }, status: 'executing', execution_duration_ms: 150 },
    ],
    latest_test_results: {
      framework: 'Vitest',
      language: 'TypeScript',
      passed: true,
      total_tests: 12,
      passed_count: 12,
      failed_count: 0,
      skipped_count: 0,
      duration_ms: 480,
      failing_tests: [],
      likely_causes: [],
      summary: 'All 12 frontend UI unit tests passed cleanly.',
    },
    steps_history: [
      { id: 's1', step_number: 1, from_state: 'RECEIVED', to_state: 'ANALYZING', step_type: 'analysis', thought_process: { action: 'Analyzing requirements' }, tool_calls: [], created_at: new Date(Date.now() - 48000).toISOString() },
      { id: 's2', step_number: 2, from_state: 'ANALYZING', to_state: 'PLANNING', step_type: 'planning', thought_process: { action: 'Generating plan' }, tool_calls: [], created_at: new Date(Date.now() - 35000).toISOString() },
      { id: 's3', step_number: 3, from_state: 'PLANNING', to_state: 'IMPLEMENTING', step_type: 'implementation', thought_process: { action: 'Writing React components' }, tool_calls: [], created_at: new Date(Date.now() - 20000).toISOString() },
    ],
    started_at: new Date(Date.now() - 48000).toISOString(),
    logs: [
      '[INFO] Agent Run Started (ID: run-993)',
      '[INFO] Transition: RECEIVED -> ANALYZING',
      '[INFO] Workspace scanned: 22 files detected',
      '[INFO] Transition: ANALYZING -> PLANNING',
      '[INFO] Implementation Plan v1 generated',
      '[INFO] Transition: PLANNING -> IMPLEMENTING',
      '[INFO] Writing components in frontend/src/components/',
      '[INFO] Tool execution: write_file frontend/src/types/agent.ts',
    ],
  },
  'run-992': {
    run_id: 'run-992',
    task_id: 'task-102',
    project_id: 'proj-agent-core',
    status: 'AWAITING_APPROVAL',
    execution_mode: 'APPROVAL_REQUIRED',
    high_risk_flagged: false,
    high_risk_triggers: [],
    user_prompt: 'Implement versioned prompt management system with Pydantic validation.',
    language_runtime: 'Python (3.11)',
    auto_approve: false,
    limits: INITIAL_LIMITS,
    current_iteration: 2,
    elapsed_seconds: 18,
    inspected_files: ['backend/app/application/agent/state_machine.py', 'backend/prompts/manifest.json'],
    modified_files: [],
    active_plan: {
      id: 'plan-102',
      goals_summary: 'Create versioned PromptManager supporting external template files, Pydantic schemas, and A/B testing.',
      plan_markdown: `# Versioned Prompt Management System Plan\n\n1. Create external prompt templates under \`prompts/\`.\n2. Create Pydantic input & output schemas in \`app/schemas/prompts.py\`.\n3. Implement \`PromptManager\` class in \`app/core/prompts/manager.py\`.\n4. Update all 6 subagents to use \`PromptManager\`.\n5. Run unit test suite.`,
      steps: [
        { step_number: 1, description: 'Create external prompt templates under prompts/', target_files: ['prompts/planner.txt', 'prompts/reviewer.txt'], action_type: 'create' },
        { step_number: 2, description: 'Implement PromptManager with Pydantic output validation', target_files: ['backend/app/core/prompts/manager.py'], action_type: 'create' },
      ],
      version: 1,
      status: 'active',
    },
    tool_calls: [
      { id: 'tc-10', tool_name: 'list_dir', tool_input: { DirectoryPath: 'prompts' }, status: 'success', execution_duration_ms: 10, output: 'planner.txt, reviewer.txt, manifest.json' }
    ],
    steps_history: [
      { id: 's10', step_number: 1, from_state: 'RECEIVED', to_state: 'ANALYZING', step_type: 'analysis', thought_process: { action: 'Analyzing requirements' }, tool_calls: [], created_at: new Date(Date.now() - 18000).toISOString() },
      { id: 's11', step_number: 2, from_state: 'ANALYZING', to_state: 'PLANNING', step_type: 'planning', thought_process: { action: 'Generating plan' }, tool_calls: [], created_at: new Date(Date.now() - 12000).toISOString() },
      { id: 's12', step_number: 3, from_state: 'PLANNING', to_state: 'AWAITING_APPROVAL', step_type: 'approval', thought_process: { action: 'Paused for plan approval' }, tool_calls: [], created_at: new Date(Date.now() - 5000).toISOString() },
    ],
    started_at: new Date(Date.now() - 18000).toISOString(),
    logs: [
      '[INFO] Agent Run Started (ID: run-992)',
      '[INFO] Transition: RECEIVED -> ANALYZING',
      '[INFO] Transition: ANALYZING -> PLANNING',
      '[INFO] Plan generated. Paused in AWAITING_APPROVAL state for user verification.',
    ],
  },
  'run-881': {
    run_id: 'run-881',
    task_id: 'task-101',
    project_id: 'proj-auth-service',
    status: 'COMPLETED',
    execution_mode: 'AUTONOMOUS',
    high_risk_flagged: false,
    high_risk_triggers: [],
    user_prompt: 'Create POST /api/v1/auth/refresh endpoint supporting refresh token rotation.',
    language_runtime: 'Python (3.11)',
    auto_approve: true,
    limits: INITIAL_LIMITS,
    current_iteration: 6,
    elapsed_seconds: 62,
    inspected_files: ['backend/app/api/v1/endpoints/auth.py', 'backend/app/core/security.py'],
    modified_files: ['backend/app/api/v1/endpoints/auth.py', 'backend/tests/test_auth.py'],
    active_plan: {
      id: 'plan-101',
      goals_summary: 'Implement token refresh rotation endpoint.',
      plan_markdown: `# JWT Refresh Token Plan\n\n1. Add endpoint to \`auth.py\`.\n2. Add test cases in \`test_auth.py\`.\n3. Run test suite.`,
      steps: [
        { step_number: 1, description: 'Add refresh endpoint', target_files: ['backend/app/api/v1/endpoints/auth.py'], action_type: 'modify' },
      ],
      version: 1,
      status: 'approved',
    },
    tool_calls: [
      { id: 'tc-20', tool_name: 'run_tests', tool_input: {}, status: 'success', execution_duration_ms: 120, output: '7 passed in 0.15s' }
    ],
    latest_test_results: {
      framework: 'pytest',
      language: 'Python',
      passed: true,
      total_tests: 7,
      passed_count: 7,
      failed_count: 0,
      skipped_count: 0,
      duration_ms: 150,
      failing_tests: [],
      likely_causes: [],
      summary: '7 passed in 0.15s',
    },
    final_review: {
      passed: true,
      summary: 'Code satisfies all security, correctness, and maintainability criteria.',
      findings: [],
      blocking_findings_count: 0,
      requires_another_cycle: false,
      timestamp: new Date(Date.now() - 3300000).toISOString(),
    },
    steps_history: [],
    started_at: new Date(Date.now() - 3600000).toISOString(),
    completed_at: new Date(Date.now() - 3300000).toISOString(),
    logs: [
      '[INFO] Execution completed successfully.',
      '[INFO] All 7 unit tests passed.',
      '[INFO] Final code review passed with 0 blocking findings.',
    ],
  }
};

// Identifier generation.
//
// `Date.now()` alone is not unique: two runs created within the same millisecond
// produce the same id, and because runs are stored as `DEFAULT_EXECUTIONS[runId]`
// the second silently overwrites the first. That is reachable in practice -
// retryTask() calls startNewTask() immediately, and any double-click on "Launch"
// does the same. A monotonic counter makes collisions impossible within a session.
let idSequence = 0;
const nextId = (prefix: string): string => {
  idSequence += 1;
  return `${prefix}-${Date.now()}-${idSequence}`;
};

export const useAgentExecutionStore = create<AgentExecutionStoreState>((set, get) => ({
  tasks: DEFAULT_TASKS,
  activeExecution: DEFAULT_EXECUTIONS['run-993'],
  isLoading: false,
  error: null,

  startNewTask: (input) => {
    const newTaskId = nextId('task');
    const newRunId = nextId('run');

    const newTask: CodingTask = {
      id: newTaskId,
      project_id: input.projectId,
      title: input.requirementPrompt.slice(0, 60) + (input.requirementPrompt.length > 60 ? '...' : ''),
      requirement_prompt: input.requirementPrompt,
      language_runtime: input.languageRuntime,
      execution_mode: input.executionMode,
      auto_approve: input.autoApprove,
      status: 'ANALYZING',
      created_at: new Date().toISOString(),
      last_run_id: newRunId,
      runs_count: 1,
    };

    const newExecution: AgentExecutionState = {
      run_id: newRunId,
      task_id: newTaskId,
      project_id: input.projectId,
      status: 'ANALYZING',
      execution_mode: input.executionMode,
      high_risk_flagged: false,
      high_risk_triggers: [],
      user_prompt: input.requirementPrompt,
      language_runtime: input.languageRuntime,
      auto_approve: input.autoApprove,
      limits: input.limits,
      current_iteration: 1,
      elapsed_seconds: 2,
      inspected_files: ['workspace_root/'],
      modified_files: [],
      active_plan: {
        id: nextId('plan'),
        goals_summary: 'Analyzing requirements and generating structured implementation plan...',
        plan_markdown: `# Implementation Plan\n\n1. Analyzing workspace structure...\n2. Identifying key files to modify...`,
        steps: [
          { step_number: 1, description: 'Scan project dependencies and entry points', target_files: ['src/'], action_type: 'modify' },
        ],
        version: 1,
        status: 'active',
      },
      tool_calls: [
        { id: 'tc-init-1', tool_name: 'list_dir', tool_input: { DirectoryPath: '.' }, status: 'success', execution_duration_ms: 15, output: 'Workspace scanned.' }
      ],
      steps_history: [
        { id: `step-1`, step_number: 1, from_state: 'RECEIVED', to_state: 'ANALYZING', step_type: 'analysis', thought_process: { action: 'Scanning project files' }, tool_calls: [], created_at: new Date().toISOString() }
      ],
      started_at: new Date().toISOString(),
      logs: [
        `[INFO] Agent Run Started (ID: ${newRunId})`,
        `[INFO] Target Project: ${input.projectId}`,
        `[INFO] Transition: RECEIVED -> ANALYZING`,
      ],
    };

    DEFAULT_EXECUTIONS[newRunId] = newExecution;

    set((state) => ({
      tasks: [newTask, ...state.tasks],
      activeExecution: newExecution,
    }));

    return newRunId;
  },

  approvePlan: (runId) => {
    set((state) => {
      if (!state.activeExecution || state.activeExecution.run_id !== runId) return state;

      const updatedExecution: AgentExecutionState = {
        ...state.activeExecution,
        status: 'IMPLEMENTING',
        logs: [
          ...state.activeExecution.logs,
          '[INFO] User approved implementation plan.',
          '[INFO] Transition: AWAITING_APPROVAL -> IMPLEMENTING',
        ],
      };

      const updatedTasks = state.tasks.map((t) =>
        t.last_run_id === runId ? { ...t, status: 'IMPLEMENTING' as AgentState } : t
      );

      return { activeExecution: updatedExecution, tasks: updatedTasks };
    });
  },

  rejectPlan: (runId, feedbackNotes) => {
    set((state) => {
      if (!state.activeExecution || state.activeExecution.run_id !== runId) return state;

      const updatedExecution: AgentExecutionState = {
        ...state.activeExecution,
        status: 'PLANNING',
        logs: [
          ...state.activeExecution.logs,
          `[WARN] User rejected implementation plan. Feedback: "${feedbackNotes || 'No notes provided'}"`,
          '[INFO] Transition: AWAITING_APPROVAL -> PLANNING',
        ],
      };

      const updatedTasks = state.tasks.map((t) =>
        t.last_run_id === runId ? { ...t, status: 'PLANNING' as AgentState } : t
      );

      return { activeExecution: updatedExecution, tasks: updatedTasks };
    });
  },

  modifyRequirements: (runId, updatedPrompt) => {
    set((state) => {
      if (!state.activeExecution || state.activeExecution.run_id !== runId) return state;

      const updatedExecution: AgentExecutionState = {
        ...state.activeExecution,
        user_prompt: updatedPrompt,
        status: 'ANALYZING',
        logs: [
          ...state.activeExecution.logs,
          `[INFO] Requirement prompt updated by user: "${updatedPrompt}"`,
          '[INFO] Transition: AWAITING_APPROVAL -> ANALYZING',
        ],
      };

      const updatedTasks = state.tasks.map((t) =>
        t.last_run_id === runId ? { ...t, requirement_prompt: updatedPrompt, status: 'ANALYZING' as AgentState } : t
      );

      return { activeExecution: updatedExecution, tasks: updatedTasks };
    });
  },

  cancelExecution: (runId) => {
    set((state) => {
      if (!state.activeExecution || state.activeExecution.run_id !== runId) return state;

      const updatedExecution: AgentExecutionState = {
        ...state.activeExecution,
        status: 'CANCELLED',
        completed_at: new Date().toISOString(),
        logs: [...state.activeExecution.logs, '[WARN] Agent execution cancelled by user.'],
      };

      const updatedTasks = state.tasks.map((t) =>
        t.last_run_id === runId ? { ...t, status: 'CANCELLED' as AgentState } : t
      );

      return { activeExecution: updatedExecution, tasks: updatedTasks };
    });
  },

  retryTask: (taskId) => {
    const task = get().tasks.find((t) => t.id === taskId);
    if (!task) return;

    get().startNewTask({
      projectId: task.project_id,
      requirementPrompt: task.requirement_prompt,
      languageRuntime: task.language_runtime,
      executionMode: task.execution_mode || 'APPROVAL_REQUIRED',
      autoApprove: task.auto_approve,
      limits: INITIAL_LIMITS,
    });
  },

  setActiveExecutionByRunId: (runId) => {
    const exec = DEFAULT_EXECUTIONS[runId];
    if (exec) {
      set({ activeExecution: exec });
    }
  },
}));
