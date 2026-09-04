import { beforeEach, describe, expect, it } from 'vitest';
import { useAgentExecutionStore } from './useAgentExecutionStore';
import type { AgentLimits } from '../types/agent';

const LIMITS: AgentLimits = {
  max_iterations: 20,
  max_execution_time: 300,
  max_tool_calls: 50,
  max_files_changed: 20,
  max_generated_output: 100000,
  max_test_attempts: 5,
  max_review_attempts: 3,
};

const NEW_TASK_INPUT = {
  projectId: 'proj-agent-core',
  requirementPrompt: 'Add a health endpoint returning build metadata',
  languageRuntime: 'Python (3.11)',
  executionMode: 'APPROVAL_REQUIRED' as const,
  autoApprove: false,
  limits: LIMITS,
};

/** Snapshot the initial store so each test starts from the same place. */
const INITIAL = useAgentExecutionStore.getState();

describe('useAgentExecutionStore', () => {
  beforeEach(() => {
    useAgentExecutionStore.setState({
      tasks: INITIAL.tasks,
      activeExecution: INITIAL.activeExecution,
      isLoading: false,
      error: null,
    });
  });

  describe('startNewTask', () => {
    it('returns a run id and makes the new run active', () => {
      const runId = useAgentExecutionStore.getState().startNewTask(NEW_TASK_INPUT);

      // `run-<epoch>-<sequence>`: the sequence suffix is what makes two runs
      // created in the same millisecond distinct.
      expect(runId).toMatch(/^run-\d+-\d+$/);
      expect(useAgentExecutionStore.getState().activeExecution?.run_id).toBe(runId);
    });

    it('prepends the task so the newest work is first', () => {
      const before = useAgentExecutionStore.getState().tasks.length;
      useAgentExecutionStore.getState().startNewTask(NEW_TASK_INPUT);

      const tasks = useAgentExecutionStore.getState().tasks;
      expect(tasks).toHaveLength(before + 1);
      expect(tasks[0].requirement_prompt).toBe(NEW_TASK_INPUT.requirementPrompt);
      expect(tasks[0].status).toBe('ANALYZING');
    });

    it('carries the execution mode and limits onto the run', () => {
      useAgentExecutionStore.getState().startNewTask(NEW_TASK_INPUT);

      const execution = useAgentExecutionStore.getState().activeExecution;
      expect(execution?.execution_mode).toBe('APPROVAL_REQUIRED');
      expect(execution?.auto_approve).toBe(false);
      expect(execution?.limits.max_iterations).toBe(20);
    });

    it('truncates a long prompt into the title but keeps the prompt intact', () => {
      const longPrompt = 'x'.repeat(120);
      useAgentExecutionStore.getState().startNewTask({
        ...NEW_TASK_INPUT,
        requirementPrompt: longPrompt,
      });

      const task = useAgentExecutionStore.getState().tasks[0];
      expect(task.title).toBe('x'.repeat(60) + '...');
      expect(task.requirement_prompt).toBe(longPrompt);
    });
  });

  describe('plan approval', () => {
    it('moves an approved run to IMPLEMENTING and logs the transition', () => {
      const runId = useAgentExecutionStore.getState().startNewTask(NEW_TASK_INPUT);
      useAgentExecutionStore.getState().approvePlan(runId);

      const execution = useAgentExecutionStore.getState().activeExecution;
      expect(execution?.status).toBe('IMPLEMENTING');
      expect(execution?.logs.some((l) => l.includes('approved'))).toBe(true);
    });

    it('keeps the task list in step with the run status', () => {
      const runId = useAgentExecutionStore.getState().startNewTask(NEW_TASK_INPUT);
      useAgentExecutionStore.getState().approvePlan(runId);

      const task = useAgentExecutionStore.getState().tasks.find((t) => t.last_run_id === runId);
      expect(task?.status).toBe('IMPLEMENTING');
    });

    it('ignores an approval aimed at a run that is not active', () => {
      // Protects against a stale UI approving the wrong run - the guard clause
      // `state.activeExecution.run_id !== runId` exists for exactly this.
      const runId = useAgentExecutionStore.getState().startNewTask(NEW_TASK_INPUT);
      const before = useAgentExecutionStore.getState().activeExecution?.status;

      useAgentExecutionStore.getState().approvePlan('run-does-not-exist');

      expect(useAgentExecutionStore.getState().activeExecution?.status).toBe(before);
      expect(useAgentExecutionStore.getState().activeExecution?.run_id).toBe(runId);
    });

    it('sends a rejected run back to PLANNING and records the feedback', () => {
      const runId = useAgentExecutionStore.getState().startNewTask(NEW_TASK_INPUT);
      useAgentExecutionStore.getState().rejectPlan(runId, 'Missing error handling');

      const execution = useAgentExecutionStore.getState().activeExecution;
      expect(execution?.status).toBe('PLANNING');
      expect(execution?.logs.some((l) => l.includes('Missing error handling'))).toBe(true);
    });

    it('records a placeholder when a rejection carries no notes', () => {
      const runId = useAgentExecutionStore.getState().startNewTask(NEW_TASK_INPUT);
      useAgentExecutionStore.getState().rejectPlan(runId);

      const logs = useAgentExecutionStore.getState().activeExecution?.logs ?? [];
      expect(logs.some((l) => l.includes('No notes provided'))).toBe(true);
    });
  });

  describe('cancellation', () => {
    it('marks the run CANCELLED and stamps a completion time', () => {
      const runId = useAgentExecutionStore.getState().startNewTask(NEW_TASK_INPUT);
      useAgentExecutionStore.getState().cancelExecution(runId);

      const execution = useAgentExecutionStore.getState().activeExecution;
      expect(execution?.status).toBe('CANCELLED');
      expect(execution?.completed_at).toBeTruthy();
    });
  });

  describe('modifyRequirements', () => {
    it('replaces the prompt and restarts analysis', () => {
      const runId = useAgentExecutionStore.getState().startNewTask(NEW_TASK_INPUT);
      useAgentExecutionStore.getState().modifyRequirements(runId, 'Completely new requirement');

      const execution = useAgentExecutionStore.getState().activeExecution;
      expect(execution?.user_prompt).toBe('Completely new requirement');
      expect(execution?.status).toBe('ANALYZING');

      const task = useAgentExecutionStore.getState().tasks.find((t) => t.last_run_id === runId);
      expect(task?.requirement_prompt).toBe('Completely new requirement');
    });
  });

  describe('retryTask', () => {
    // Regression test: startNewTask used to derive ids from Date.now() alone, so
    // a retry in the same millisecond produced a duplicate run id and clobbered
    // the previous run's record.
    it('creates a new run reusing the original requirement', () => {
      const firstRun = useAgentExecutionStore.getState().startNewTask(NEW_TASK_INPUT);
      const taskId = useAgentExecutionStore.getState().tasks[0].id;
      const countBefore = useAgentExecutionStore.getState().tasks.length;

      useAgentExecutionStore.getState().retryTask(taskId);

      const state = useAgentExecutionStore.getState();
      expect(state.tasks).toHaveLength(countBefore + 1);
      expect(state.activeExecution?.run_id).not.toBe(firstRun);
      expect(state.activeExecution?.user_prompt).toBe(NEW_TASK_INPUT.requirementPrompt);
    });

    it('does nothing for an unknown task id', () => {
      const countBefore = useAgentExecutionStore.getState().tasks.length;
      useAgentExecutionStore.getState().retryTask('task-nope');
      expect(useAgentExecutionStore.getState().tasks).toHaveLength(countBefore);
    });
  });

  describe('setActiveExecutionByRunId', () => {
    it('switches to a known run', () => {
      useAgentExecutionStore.getState().setActiveExecutionByRunId('run-992');
      expect(useAgentExecutionStore.getState().activeExecution?.run_id).toBe('run-992');
    });

    it('leaves the active run untouched for an unknown id', () => {
      useAgentExecutionStore.getState().setActiveExecutionByRunId('run-992');
      useAgentExecutionStore.getState().setActiveExecutionByRunId('run-unknown');
      expect(useAgentExecutionStore.getState().activeExecution?.run_id).toBe('run-992');
    });
  });
});
