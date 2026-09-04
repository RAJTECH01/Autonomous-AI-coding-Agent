import React, { useState } from 'react';
import { useProjectStore } from '../store/useProjectStore';
import { useAgentExecutionStore } from '../store/useAgentExecutionStore';
import { useNavigationStore } from '../store/useNavigationStore';
import { PlusCircle, Sliders, ShieldCheck, Play, ArrowLeft } from 'lucide-react';
import { AgentLimits, ExecutionMode } from '../types/agent';

export const NewCodingTaskPage: React.FC = () => {
  const { projects } = useProjectStore();
  const { startNewTask } = useAgentExecutionStore();
  const { params, navigate } = useNavigationStore();

  const [projectId, setProjectId] = useState(params.projectId || projects[0]?.id || '');
  const [requirementPrompt, setRequirementPrompt] = useState('');
  const [languageRuntime, setLanguageRuntime] = useState('Python (3.11)');
  const [executionMode, setExecutionMode] = useState<ExecutionMode>('APPROVAL_REQUIRED');
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Execution Limits Config
  const [limits, setLimits] = useState<AgentLimits>({
    max_iterations: 20,
    max_execution_time: 300,
    max_tool_calls: 50,
    max_files_changed: 20,
    max_generated_output: 100000,
    max_test_attempts: 5,
    max_review_attempts: 3,
  });

  const [error, setError] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!requirementPrompt.trim()) {
      setError('Please provide a natural language software requirement prompt.');
      return;
    }

    const runId = startNewTask({
      projectId,
      requirementPrompt,
      languageRuntime,
      executionMode,
      autoApprove: executionMode === 'AUTONOMOUS',
      limits,
    });

    navigate('agent_execution', { taskId: `task-${Date.now()}`, runId });
  };

  return (
    <div style={{ maxWidth: '840px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
      {/* Top Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <button
            onClick={() => navigate('dashboard')}
            className="btn btn-secondary"
            style={{ padding: '0.45rem 0.85rem', fontSize: '0.85rem' }}
          >
            <ArrowLeft size={16} /> Back
          </button>
          <div>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <PlusCircle size={26} color="var(--accent-cyan)" style={{ filter: 'drop-shadow(0 0 6px var(--accent-cyan-glow))' }} /> Create New Autonomous Coding Task
            </h2>
            <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
              Define the software goal, target project, execution limits, and human approval workflow.
            </p>
          </div>
        </div>
      </div>

      {error && (
        <div
          style={{
            background: 'linear-gradient(135deg, rgba(244, 63, 94, 0.2) 0%, rgba(185, 28, 28, 0.15) 100%)',
            border: '1px solid rgba(251, 113, 133, 0.35)',
            color: '#fca5a5',
            padding: '0.9rem',
            borderRadius: '12px',
            fontSize: '0.88rem',
            boxShadow: '0 4px 12px rgba(244,63,94,0.2)',
          }}
        >
          {error}
        </div>
      )}

      {/* Task Definition Form */}
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
        {/* Section 1: Requirement & Project */}
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.35rem' }}>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 800, color: 'var(--text-main)' }}>
            1. Software Requirement & Project Context
          </h3>

          <div>
            <label style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-muted)', display: 'block', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Requirement Prompt *
            </label>
            <textarea
              rows={5}
              value={requirementPrompt}
              onChange={(e) => setRequirementPrompt(e.target.value)}
              placeholder="e.g. Implement a new REST endpoint POST /api/v1/auth/refresh in FastAPI. Support refresh token rotation, revocation validation against database, and unit tests."
              required
            />
            <span style={{ fontSize: '0.78rem', color: 'var(--text-dim)', marginTop: '0.4rem', display: 'block' }}>
              Describe functional expectations, language constraints, and target endpoint behavior.
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.35rem' }}>
            <div>
              <label style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-muted)', display: 'block', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Select Project Workspace *
              </label>
              <select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.language})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-muted)', display: 'block', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Allowed Language & Runtime *
              </label>
              <select value={languageRuntime} onChange={(e) => setLanguageRuntime(e.target.value)}>
                <option value="Python (3.11)">Python (3.11 + pytest)</option>
                <option value="TypeScript (Node 20)">TypeScript (Node 20 + Vitest / Jest)</option>
                <option value="Go (1.22)">Go (1.22 + go test)</option>
                <option value="Rust (1.76)">Rust (Cargo test)</option>
                <option value="Java (21)">Java (OpenSDK 21 + JUnit 5)</option>
              </select>
            </div>
          </div>
        </div>

        {/* Section 2: Human Approval & Execution Workflow */}
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.1rem' }}>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 800, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <ShieldCheck size={20} color="#34d399" style={{ filter: 'drop-shadow(0 0 6px rgba(52,211,153,0.5))' }} /> 2. Human-in-the-Loop Execution Mode
          </h3>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1.1rem' }}>
            {/* PLAN_ONLY */}
            <div
              onClick={() => setExecutionMode('PLAN_ONLY')}
              style={{
                padding: '1.1rem',
                borderRadius: '14px',
                background: executionMode === 'PLAN_ONLY' ? 'linear-gradient(135deg, rgba(0, 242, 254, 0.2) 0%, rgba(59, 130, 246, 0.2) 100%)' : 'rgba(5, 9, 18, 0.65)',
                border: executionMode === 'PLAN_ONLY' ? '1px solid rgba(0, 242, 254, 0.6)' : '1px solid var(--glass-border)',
                boxShadow: executionMode === 'PLAN_ONLY' ? '0 8px 24px -4px rgba(0, 242, 254, 0.3), inset 0 1px 1px rgba(255, 255, 255, 0.4)' : 'var(--skeuo-shadow-inset)',
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.45rem',
                transition: 'all 0.2s ease',
              }}
            >
              <span style={{ fontSize: '0.92rem', fontWeight: 800, color: 'var(--accent-cyan)' }}>1. PLAN_ONLY</span>
              <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', lineHeight: '1.45' }}>
                Generates architecture & implementation plan without modifying any code files.
              </span>
            </div>

            {/* APPROVAL_REQUIRED */}
            <div
              onClick={() => setExecutionMode('APPROVAL_REQUIRED')}
              style={{
                padding: '1.1rem',
                borderRadius: '14px',
                background: executionMode === 'APPROVAL_REQUIRED' ? 'linear-gradient(135deg, rgba(245, 158, 11, 0.2) 0%, rgba(217, 119, 6, 0.2) 100%)' : 'rgba(5, 9, 18, 0.65)',
                border: executionMode === 'APPROVAL_REQUIRED' ? '1px solid rgba(251, 191, 36, 0.6)' : '1px solid var(--glass-border)',
                boxShadow: executionMode === 'APPROVAL_REQUIRED' ? '0 8px 24px -4px rgba(245, 158, 11, 0.3), inset 0 1px 1px rgba(255, 255, 255, 0.4)' : 'var(--skeuo-shadow-inset)',
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.45rem',
                transition: 'all 0.2s ease',
              }}
            >
              <span style={{ fontSize: '0.92rem', fontWeight: 800, color: '#fbbf24' }}>2. APPROVAL_REQUIRED</span>
              <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', lineHeight: '1.45' }}>
                Pauses after plan generation. User must approve, reject, cancel, or modify requirements.
              </span>
            </div>

            {/* AUTONOMOUS */}
            <div
              onClick={() => setExecutionMode('AUTONOMOUS')}
              style={{
                padding: '1.1rem',
                borderRadius: '14px',
                background: executionMode === 'AUTONOMOUS' ? 'linear-gradient(135deg, rgba(16, 185, 129, 0.2) 0%, rgba(5, 150, 105, 0.2) 100%)' : 'rgba(5, 9, 18, 0.65)',
                border: executionMode === 'AUTONOMOUS' ? '1px solid rgba(52, 211, 153, 0.6)' : '1px solid var(--glass-border)',
                boxShadow: executionMode === 'AUTONOMOUS' ? '0 8px 24px -4px rgba(16, 185, 129, 0.3), inset 0 1px 1px rgba(255, 255, 255, 0.4)' : 'var(--skeuo-shadow-inset)',
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.45rem',
                transition: 'all 0.2s ease',
              }}
            >
              <span style={{ fontSize: '0.92rem', fontWeight: 800, color: '#34d399' }}>3. AUTONOMOUS</span>
              <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', lineHeight: '1.45' }}>
                Runs end-to-end. Mandatory High-Risk override policy pauses for human approval if security/DB/config is touched.
              </span>
            </div>
          </div>
        </div>

        {/* Section 3: Execution Limits Configuration */}
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 800, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <Sliders size={20} color="var(--accent-purple)" style={{ filter: 'drop-shadow(0 0 6px var(--accent-purple-glow))' }} /> 3. Resource & Safety Limits
            </h3>
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              style={{ background: 'transparent', border: 'none', color: 'var(--accent-cyan)', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 700 }}
            >
              {showAdvanced ? 'Hide Custom Limits' : 'Configure Custom Limits'}
            </button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1.1rem' }}>
            <div>
              <label style={{ fontSize: '0.78rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.35rem', fontWeight: 700, textTransform: 'uppercase' }}>
                Max Iterations
              </label>
              <input
                type="number"
                value={limits.max_iterations}
                onChange={(e) => setLimits({ ...limits, max_iterations: parseInt(e.target.value) || 1 })}
                min={1}
                max={50}
              />
            </div>

            <div>
              <label style={{ fontSize: '0.78rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.35rem', fontWeight: 700, textTransform: 'uppercase' }}>
                Max Execution Time (sec)
              </label>
              <input
                type="number"
                value={limits.max_execution_time}
                onChange={(e) => setLimits({ ...limits, max_execution_time: parseInt(e.target.value) || 30 })}
                min={30}
                max={3600}
              />
            </div>

            <div>
              <label style={{ fontSize: '0.78rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.35rem', fontWeight: 700, textTransform: 'uppercase' }}>
                Max Tool Calls
              </label>
              <input
                type="number"
                value={limits.max_tool_calls}
                onChange={(e) => setLimits({ ...limits, max_tool_calls: parseInt(e.target.value) || 10 })}
                min={10}
                max={200}
              />
            </div>
          </div>

          {showAdvanced && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1.1rem', paddingTop: '0.6rem' }}>
              <div>
                <label style={{ fontSize: '0.78rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.35rem', fontWeight: 700, textTransform: 'uppercase' }}>
                  Max Files Changed
                </label>
                <input
                  type="number"
                  value={limits.max_files_changed}
                  onChange={(e) => setLimits({ ...limits, max_files_changed: parseInt(e.target.value) || 1 })}
                  min={1}
                  max={50}
                />
              </div>

              <div>
                <label style={{ fontSize: '0.78rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.35rem', fontWeight: 700, textTransform: 'uppercase' }}>
                  Max Test Attempts
                </label>
                <input
                  type="number"
                  value={limits.max_test_attempts}
                  onChange={(e) => setLimits({ ...limits, max_test_attempts: parseInt(e.target.value) || 1 })}
                  min={1}
                  max={10}
                />
              </div>

              <div>
                <label style={{ fontSize: '0.78rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.35rem', fontWeight: 700, textTransform: 'uppercase' }}>
                  Max Review Attempts
                </label>
                <input
                  type="number"
                  value={limits.max_review_attempts}
                  onChange={(e) => setLimits({ ...limits, max_review_attempts: parseInt(e.target.value) || 1 })}
                  min={1}
                  max={10}
                />
              </div>
            </div>
          )}
        </div>

        {/* Start Task Submit Button */}
        <button
          type="submit"
          className="btn"
          style={{
            padding: '1.1rem 2.25rem',
            fontSize: '1.05rem',
          }}
        >
          <Play size={22} /> Start Autonomous Agent Execution
        </button>
      </form>
    </div>
  );
};
