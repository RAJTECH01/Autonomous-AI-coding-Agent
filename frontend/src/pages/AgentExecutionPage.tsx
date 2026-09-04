import React, { useState } from 'react';
import { useAgentExecutionStore } from '../store/useAgentExecutionStore';
import { useProjectStore } from '../store/useProjectStore';
import { useNavigationStore } from '../store/useNavigationStore';
import { ExecutionLiveMetrics } from '../components/agent/ExecutionLiveMetrics';
import { PlanViewer } from '../components/agent/PlanViewer';
import { ToolCallList } from '../components/agent/ToolCallList';
import { TestResultsViewer } from '../components/agent/TestResultsViewer';
import { ReviewFindingsViewer } from '../components/agent/ReviewFindingsViewer';
import { FileViewer } from '../components/agent/FileViewer';
import { LogViewer } from '../components/agent/LogViewer';
import { GitDiffViewer } from '../components/agent/GitDiffViewer';
import { ObservabilityDashboard } from '../components/agent/ObservabilityDashboard';
import { Tabs } from '../components/common/Tabs';
import { EmptyState } from '../components/common/EmptyState';
import { PlayCircle, CheckCircle2, PauseCircle, XCircle, AlertTriangle, ArrowLeft, Edit3, X } from 'lucide-react';

export const AgentExecutionPage: React.FC = () => {
  const { activeExecution, approvePlan, rejectPlan, cancelExecution, modifyRequirements } = useAgentExecutionStore();
  const { projectFiles } = useProjectStore();
  const { navigate } = useNavigationStore();

  const [activeTab, setActiveTab] = useState<'plan' | 'tools' | 'tests' | 'errors' | 'files' | 'git' | 'observability' | 'review' | 'logs'>('plan');

  // Modals for Human-in-the-loop controls
  const [isRejectModalOpen, setIsRejectModalOpen] = useState(false);
  const [rejectFeedback, setRejectFeedback] = useState('');

  const [isModifyModalOpen, setIsModifyModalOpen] = useState(false);
  const [updatedPromptText, setUpdatedPromptText] = useState('');

  if (!activeExecution) {
    return (
      <EmptyState
        title="No Active Execution Selected"
        description="Select a running coding task from the dashboard or create a new task to view live execution details."
        actionLabel="Launch New Coding Task"
        onAction={() => navigate('new_task')}
      />
    );
  }

  const files = projectFiles[activeExecution.project_id] || [];

  const handleConfirmReject = (e: React.FormEvent) => {
    e.preventDefault();
    rejectPlan(activeExecution.run_id, rejectFeedback);
    setIsRejectModalOpen(false);
    setRejectFeedback('');
  };

  const handleConfirmModifyPrompt = (e: React.FormEvent) => {
    e.preventDefault();
    if (!updatedPromptText.trim()) return;
    modifyRequirements(activeExecution.run_id, updatedPromptText);
    setIsModifyModalOpen(false);
    setUpdatedPromptText('');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
      {/* Top Header & Actions */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <button
            onClick={() => navigate('dashboard')}
            className="btn btn-secondary"
            style={{ padding: '0.45rem 0.85rem', fontSize: '0.85rem' }}
          >
            <ArrowLeft size={16} /> Dashboard
          </button>

          <div>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <PlayCircle size={26} color="var(--accent-cyan)" style={{ filter: 'drop-shadow(0 0 6px var(--accent-cyan-glow))' }} /> Agent Execution Cockpit
            </h2>
            <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              Run ID: <strong style={{ color: 'var(--accent-cyan)' }}>{activeExecution.run_id}</strong> • Mode: {activeExecution.execution_mode || 'APPROVAL_REQUIRED'}
            </span>
          </div>
        </div>

        {/* Top Action Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {activeExecution.status === 'AWAITING_APPROVAL' && (
            <>
              <button
                className="btn"
                onClick={() => approvePlan(activeExecution.run_id)}
                style={{
                  background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.9) 0%, rgba(5, 150, 105, 0.9) 100%)',
                  padding: '0.6rem 1.25rem',
                  fontSize: '0.86rem',
                }}
              >
                <CheckCircle2 size={16} /> Approve Plan
              </button>

              <button
                onClick={() => setIsRejectModalOpen(true)}
                style={{
                  background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.25) 0%, rgba(217, 119, 6, 0.25) 100%)',
                  border: '1px solid rgba(251, 191, 36, 0.4)',
                  color: '#fbbf24',
                  padding: '0.6rem 1.1rem',
                  borderRadius: '12px',
                  cursor: 'pointer',
                  fontWeight: 700,
                  fontSize: '0.86rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.45rem',
                  boxShadow: 'var(--skeuo-shadow-raised)',
                }}
              >
                <XCircle size={16} /> Reject Plan
              </button>

              <button
                onClick={() => {
                  setUpdatedPromptText(activeExecution.user_prompt);
                  setIsModifyModalOpen(true);
                }}
                className="btn btn-secondary"
                style={{
                  padding: '0.6rem 1.1rem',
                  fontSize: '0.86rem',
                }}
              >
                <Edit3 size={16} color="var(--accent-cyan)" /> Modify Prompt
              </button>
            </>
          )}

          {!['COMPLETED', 'FAILED', 'CANCELLED'].includes(activeExecution.status) && (
            <button
              onClick={() => cancelExecution(activeExecution.run_id)}
              className="btn btn-danger"
              style={{
                padding: '0.6rem 1.1rem',
                fontSize: '0.86rem',
              }}
            >
              <X size={16} /> Cancel Run
            </button>
          )}
        </div>
      </div>

      {/* Requirement Banner */}
      <div className="glass-panel" style={{ borderLeft: '4px solid var(--accent-purple)', padding: '1.25rem 1.5rem' }}>
        <span style={{ fontSize: '0.72rem', fontWeight: 800, color: 'var(--accent-purple)', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'block', marginBottom: '0.35rem' }}>
          Target Requirement Prompt
        </span>
        <p style={{ fontSize: '0.95rem', color: 'var(--text-main)', lineHeight: '1.55' }}>
          {activeExecution.user_prompt}
        </p>
      </div>

      {/* Live Metrics Cards */}
      <ExecutionLiveMetrics execution={activeExecution} />

      {/* High Risk Mandatory Override Alert Banner */}
      {activeExecution.high_risk_flagged && (
        <div
          style={{
            background: 'linear-gradient(135deg, rgba(244, 63, 94, 0.2) 0%, rgba(185, 28, 28, 0.15) 100%)',
            border: '1px solid rgba(251, 113, 133, 0.4)',
            borderRadius: '14px',
            padding: '1.35rem',
            color: '#fca5a5',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.6rem',
            boxShadow: '0 8px 24px -4px rgba(244,63,94,0.3)',
            backdropFilter: 'blur(16px)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <AlertTriangle size={24} color="#fb7185" style={{ filter: 'drop-shadow(0 0 6px rgba(244,63,94,0.6))' }} />
            <h4 style={{ fontSize: '1.05rem', fontWeight: 800, color: '#fb7185' }}>
              HIGH-RISK ACTION FLAGGED BY APPROVAL POLICY ENGINE
            </h4>
          </div>
          <p style={{ fontSize: '0.9rem', color: 'var(--text-main)', lineHeight: 1.5 }}>
            The policy engine detected high-risk operations (e.g. auth changes, DB schema, or file deletion). Mandatory human approval is required before execution can proceed.
          </p>
          {activeExecution.high_risk_triggers && activeExecution.high_risk_triggers.length > 0 && (
            <ul style={{ paddingLeft: '1.35rem', fontSize: '0.85rem', color: '#fca5a5' }}>
              {activeExecution.high_risk_triggers.map((trig, idx) => (
                <li key={idx}>{trig}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Human Approval Required Alert & Actions */}
      {activeExecution.status === 'AWAITING_APPROVAL' && (
        <div
          style={{
            background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.2) 0%, rgba(217, 119, 6, 0.15) 100%)',
            border: '1px solid rgba(251, 191, 36, 0.4)',
            borderRadius: '14px',
            padding: '1.35rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            color: '#fef08a',
            boxShadow: '0 8px 24px -4px rgba(245,158,11,0.25)',
            backdropFilter: 'blur(16px)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.95rem' }}>
            <PauseCircle size={30} color="#fbbf24" style={{ filter: 'drop-shadow(0 0 6px rgba(245,158,11,0.5))' }} />
            <div>
              <h4 style={{ fontSize: '1.05rem', fontWeight: 800, color: '#fbbf24' }}>
                Human Verification & Approval Required
              </h4>
              <p style={{ fontSize: '0.9rem', color: 'var(--text-main)', marginTop: '0.35rem' }}>
                Review the implementation plan below. Choose an action to proceed, reject, or modify requirements.
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button
              className="btn"
              onClick={() => approvePlan(activeExecution.run_id)}
              style={{ background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.9) 0%, rgba(5, 150, 105, 0.9) 100%)', padding: '0.65rem 1.25rem', fontSize: '0.88rem' }}
            >
              Approve Plan & Proceed
            </button>

            <button
              onClick={() => setIsRejectModalOpen(true)}
              style={{ background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.25) 0%, rgba(217, 119, 6, 0.25) 100%)', border: '1px solid rgba(251, 191, 36, 0.4)', color: '#fbbf24', padding: '0.65rem 1.1rem', borderRadius: '12px', cursor: 'pointer', fontWeight: 700, fontSize: '0.88rem' }}
            >
              Reject Plan
            </button>
          </div>
        </div>
      )}

      {/* Main Tabs Navigation */}
      <Tabs
        tabs={[
          { id: 'plan', label: 'Implementation Plan', badge: activeExecution.active_plan?.steps.length },
          { id: 'tools', label: 'Tool Calls', badge: activeExecution.tool_calls.length },
          { id: 'tests', label: 'Test Results', badge: activeExecution.latest_test_results ? (activeExecution.latest_test_results.passed ? 'PASSED' : 'FAILED') : undefined },
          { id: 'errors', label: 'Errors & Fixes', badge: activeExecution.latest_error ? 'ERROR' : undefined },
          { id: 'files', label: 'Files Inspected / Modified', badge: activeExecution.modified_files.length },
          { id: 'git', label: 'Git & Code Diff', badge: activeExecution.modified_files.length > 0 ? 'DIFF' : undefined },
          { id: 'observability', label: 'Observability & Metrics', badge: 'LIVE' },
          { id: 'review', label: 'Final Code Review', badge: activeExecution.final_review ? 'PASSED' : undefined },
          { id: 'logs', label: 'Log Stream', badge: activeExecution.logs.length },
        ]}
        activeTab={activeTab}
        onChange={(id) => setActiveTab(id as any)}
      />

      {/* Tab Content Panels */}
      {activeTab === 'plan' && <PlanViewer plan={activeExecution.active_plan} />}
      {activeTab === 'tools' && <ToolCallList toolCalls={activeExecution.tool_calls} />}
      {activeTab === 'tests' && <TestResultsViewer testResults={activeExecution.latest_test_results} />}

      {activeTab === 'errors' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {activeExecution.latest_error ? (
            <div className="glass-panel" style={{ borderLeft: '4px solid #fb7185' }}>
              <h4 style={{ fontSize: '1.05rem', fontWeight: 800, color: '#fb7185', marginBottom: '0.6rem', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                <AlertTriangle size={20} color="#fb7185" style={{ filter: 'drop-shadow(0 0 6px rgba(244,63,94,0.5))' }} /> Runtime Error Stack Trace
              </h4>
              <p style={{ fontSize: '0.9rem', color: '#fca5a5', marginBottom: '0.85rem', fontWeight: 600 }}>
                {activeExecution.latest_error.error_type}: {activeExecution.latest_error.root_cause || 'Exception occurred during step execution.'}
              </p>
              <pre className="skeuo-inset" style={{ color: '#fb7185', fontSize: '0.82rem', padding: '1.1rem', borderRadius: '10px' }}>
                {activeExecution.latest_error.stack_trace}
              </pre>
            </div>
          ) : (
            <div className="glass-panel" style={{ color: 'var(--text-muted)', fontSize: '0.95rem', padding: '2rem', textAlign: 'center' }}>
              No runtime errors recorded in this execution run.
            </div>
          )}

          {activeExecution.latest_fix && (
            <div className="glass-panel" style={{ borderLeft: '4px solid #34d399' }}>
              <h4 style={{ fontSize: '1.05rem', fontWeight: 800, color: '#34d399', marginBottom: '0.6rem' }}>
                Applied Code Fix Strategy
              </h4>
              <p style={{ fontSize: '0.92rem', color: 'var(--text-main)', marginBottom: '0.85rem', lineHeight: 1.5 }}>
                {activeExecution.latest_fix.proposed_fix}
              </p>
              <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                Affected Files: {activeExecution.latest_fix.affected_files.join(', ')}
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'files' && (
        <FileViewer
          files={files}
          inspectedFiles={activeExecution.inspected_files}
          modifiedFiles={activeExecution.modified_files}
        />
      )}

      {activeTab === 'git' && <GitDiffViewer />}
      {activeTab === 'observability' && <ObservabilityDashboard />}

      {activeTab === 'review' && <ReviewFindingsViewer review={activeExecution.final_review} />}
      {activeTab === 'logs' && <LogViewer logs={activeExecution.logs} />}

      {/* Reject Plan Modal */}
      {isRejectModalOpen && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(3, 7, 18, 0.8)', backdropFilter: 'blur(16px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div className="glass-panel" style={{ width: '100%', maxWidth: '500px', padding: '2.25rem', border: '1px solid rgba(255, 255, 255, 0.25)', boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.8)' }}>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 800, color: '#fbbf24', marginBottom: '0.85rem' }}>
              Reject Implementation Plan
            </h3>
            <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: '1.35rem', lineHeight: 1.5 }}>
              Provide feedback notes explaining why the plan was rejected. The agent will re-enter the planning phase to generate a revised plan.
            </p>

            <form onSubmit={handleConfirmReject} style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem' }}>
              <textarea
                rows={4}
                value={rejectFeedback}
                onChange={(e) => setRejectFeedback(e.target.value)}
                placeholder="e.g. Please do not modify auth/security.py directly. Use dependency injection middleware instead..."
                required
              />

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.85rem', marginTop: '0.6rem' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setIsRejectModalOpen(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn" style={{ background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.9) 0%, rgba(217, 119, 6, 0.9) 100%)', color: '#030712', fontWeight: 800 }}>
                  Confirm Rejection
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modify Requirements Modal */}
      {isModifyModalOpen && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(3, 7, 18, 0.8)', backdropFilter: 'blur(16px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div className="glass-panel" style={{ width: '100%', maxWidth: '540px', padding: '2.25rem', border: '1px solid rgba(255, 255, 255, 0.25)', boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.8)' }}>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--accent-cyan)', marginBottom: '0.85rem' }}>
              Modify Requirement Prompt & Re-Analyze
            </h3>
            <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: '1.35rem', lineHeight: 1.5 }}>
              Update the software requirement prompt. The agent will reset state to ANALYZING and generate a fresh architecture plan.
            </p>

            <form onSubmit={handleConfirmModifyPrompt} style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem' }}>
              <textarea
                rows={5}
                value={updatedPromptText}
                onChange={(e) => setUpdatedPromptText(e.target.value)}
                required
              />

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.85rem', marginTop: '0.6rem' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setIsModifyModalOpen(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn">
                  Re-Analyze & Plan
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
