import React, { useEffect, useState } from 'react';
import { AgentExecutionState } from '../../types/agent';
import { AgentStateBadge } from './AgentStateBadge';
import { Clock, RefreshCw, FileCode, Wrench } from 'lucide-react';

interface ExecutionLiveMetricsProps {
  execution: AgentExecutionState;
}

export const ExecutionLiveMetrics: React.FC<ExecutionLiveMetricsProps> = ({ execution }) => {
  const [seconds, setSeconds] = useState(execution.elapsed_seconds || 0);

  useEffect(() => {
    if (['COMPLETED', 'FAILED', 'CANCELLED', 'AWAITING_APPROVAL'].includes(execution.status)) {
      return;
    }
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, [execution.status]);

  const formatTime = (secs: number) => {
    const mins = Math.floor(secs / 60);
    const remainingSecs = secs % 60;
    return `${mins}m ${remainingSecs < 10 ? '0' : ''}${remainingSecs}s`;
  };

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))',
        gap: '1.2rem',
      }}
    >
      <div className="glass-panel glass-panel-interactive" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 800, letterSpacing: '0.05em' }}>Agent Status</span>
        <div>
          <AgentStateBadge state={execution.status} />
        </div>
      </div>

      <div className="glass-panel glass-panel-interactive" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 800, letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <Clock size={15} color="var(--accent-cyan)" style={{ filter: 'drop-shadow(0 0 4px var(--accent-cyan-glow))' }} /> Elapsed Time
        </span>
        <span style={{ fontSize: '1.35rem', fontWeight: 800, fontFamily: 'var(--font-mono)', color: '#fff', textShadow: '0 0 10px rgba(0, 242, 254, 0.4)' }}>
          {formatTime(seconds)}
        </span>
      </div>

      <div className="glass-panel glass-panel-interactive" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 800, letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <RefreshCw size={15} color="var(--accent-purple)" style={{ filter: 'drop-shadow(0 0 4px var(--accent-purple-glow))' }} /> Iteration Count
        </span>
        <span style={{ fontSize: '1.35rem', fontWeight: 800, fontFamily: 'var(--font-mono)', color: '#fff', textShadow: '0 0 10px rgba(157, 78, 221, 0.4)' }}>
          {execution.current_iteration} <span style={{ fontSize: '0.9rem', color: 'var(--text-dim)' }}>/ {execution.limits.max_iterations}</span>
        </span>
      </div>

      <div className="glass-panel glass-panel-interactive" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 800, letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <FileCode size={15} color="var(--accent-emerald)" style={{ filter: 'drop-shadow(0 0 4px var(--accent-emerald-glow))' }} /> Modified / Inspected
        </span>
        <span style={{ fontSize: '1.35rem', fontWeight: 800, fontFamily: 'var(--font-mono)', color: '#fff', textShadow: '0 0 10px rgba(16, 185, 129, 0.4)' }}>
          {execution.modified_files.length} <span style={{ fontSize: '0.9rem', color: 'var(--text-dim)' }}>/ {execution.inspected_files.length}</span>
        </span>
      </div>

      <div className="glass-panel glass-panel-interactive" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 800, letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <Wrench size={15} color="var(--accent-blue)" style={{ filter: 'drop-shadow(0 0 4px rgba(59, 130, 246, 0.5))' }} /> Tool Executions
        </span>
        <span style={{ fontSize: '1.35rem', fontWeight: 800, fontFamily: 'var(--font-mono)', color: '#fff', textShadow: '0 0 10px rgba(59, 130, 246, 0.4)' }}>
          {execution.tool_calls.length} <span style={{ fontSize: '0.9rem', color: 'var(--text-dim)' }}>/ {execution.limits.max_tool_calls}</span>
        </span>
      </div>
    </div>
  );
};
