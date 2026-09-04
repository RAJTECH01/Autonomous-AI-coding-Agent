import React from 'react';
import { useProjectStore } from '../store/useProjectStore';
import { useAgentExecutionStore } from '../store/useAgentExecutionStore';
import { useNavigationStore } from '../store/useNavigationStore';
import { AgentStateBadge } from '../components/agent/AgentStateBadge';
import { PlusCircle, Folder, PlayCircle, ShieldCheck, CheckCircle2, ArrowRight, Activity } from 'lucide-react';

export const DashboardPage: React.FC = () => {
  const { projects } = useProjectStore();
  const { tasks } = useAgentExecutionStore();
  const { navigate } = useNavigationStore();

  const completedCount = tasks.filter((t) => t.status === 'COMPLETED').length;
  const runningCount = tasks.filter((t) => !['COMPLETED', 'FAILED', 'CANCELLED'].includes(t.status)).length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
      {/* Welcome Banner */}
      <div
        className="glass-panel"
        style={{
          background: 'linear-gradient(135deg, rgba(0, 242, 254, 0.25) 0%, rgba(157, 78, 221, 0.25) 100%)',
          border: '1px solid rgba(0, 242, 254, 0.4)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '2rem 2.25rem',
          boxShadow: '0 16px 40px -10px rgba(0, 242, 254, 0.25), var(--skeuo-shadow-card)',
        }}
      >
        <div>
          <h2 style={{ fontSize: '1.65rem', fontWeight: 800, color: '#fff', marginBottom: '0.4rem', letterSpacing: '-0.02em', textShadow: '0 2px 10px rgba(0,0,0,0.5)' }}>
            Autonomous Coding Agent Command Center
          </h2>
          <p style={{ fontSize: '0.95rem', color: 'var(--text-muted)', maxWidth: '640px', lineHeight: 1.5 }}>
            Orchestrate end-to-end coding tasks, sandbox execution, automated testing, and 12-criterion code reviews in isolated Docker / gVisor environments.
          </p>
        </div>

        <button
          className="btn"
          onClick={() => navigate('new_task')}
          style={{ padding: '0.9rem 1.75rem', fontSize: '0.96rem' }}
        >
          <PlusCircle size={20} /> Launch New Coding Task
        </button>
      </div>

      {/* Overview Stat Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1.25rem' }}>
        <div className="glass-panel glass-panel-interactive" style={{ display: 'flex', alignItems: 'center', gap: '1.1rem', padding: '1.25rem' }}>
          <div style={{ padding: '0.9rem', borderRadius: '14px', background: 'linear-gradient(135deg, rgba(0, 242, 254, 0.3) 0%, rgba(59, 130, 246, 0.3) 100%)', color: 'var(--accent-cyan)', boxShadow: '0 6px 16px rgba(0,242,254,0.25), inset 0 1px 1px rgba(255,255,255,0.4)', border: '1px solid rgba(0,242,254,0.4)' }}>
            <Folder size={24} style={{ filter: 'drop-shadow(0 0 4px var(--accent-cyan-glow))' }} />
          </div>
          <div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 800, letterSpacing: '0.05em' }}>Workspaces</span>
            <span style={{ fontSize: '1.6rem', fontWeight: 800, color: '#fff', display: 'block', textShadow: '0 2px 4px rgba(0,0,0,0.5)' }}>{projects.length}</span>
          </div>
        </div>

        <div className="glass-panel glass-panel-interactive" style={{ display: 'flex', alignItems: 'center', gap: '1.1rem', padding: '1.25rem' }}>
          <div style={{ padding: '0.9rem', borderRadius: '14px', background: 'linear-gradient(135deg, rgba(157, 78, 221, 0.3) 0%, rgba(123, 44, 191, 0.3) 100%)', color: 'var(--accent-purple)', boxShadow: '0 6px 16px rgba(157,78,221,0.25), inset 0 1px 1px rgba(255,255,255,0.4)', border: '1px solid rgba(157,78,221,0.4)' }}>
            <Activity size={24} style={{ filter: 'drop-shadow(0 0 4px var(--accent-purple-glow))' }} />
          </div>
          <div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 800, letterSpacing: '0.05em' }}>Running Tasks</span>
            <span style={{ fontSize: '1.6rem', fontWeight: 800, color: '#fff', display: 'block', textShadow: '0 2px 4px rgba(0,0,0,0.5)' }}>{runningCount}</span>
          </div>
        </div>

        <div className="glass-panel glass-panel-interactive" style={{ display: 'flex', alignItems: 'center', gap: '1.1rem', padding: '1.25rem' }}>
          <div style={{ padding: '0.9rem', borderRadius: '14px', background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.3) 0%, rgba(5, 150, 105, 0.3) 100%)', color: '#34d399', boxShadow: '0 6px 16px rgba(16,185,129,0.25), inset 0 1px 1px rgba(255,255,255,0.4)', border: '1px solid rgba(52,211,153,0.4)' }}>
            <CheckCircle2 size={24} style={{ filter: 'drop-shadow(0 0 4px rgba(52,211,153,0.5))' }} />
          </div>
          <div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 800, letterSpacing: '0.05em' }}>Completed Tasks</span>
            <span style={{ fontSize: '1.6rem', fontWeight: 800, color: '#fff', display: 'block', textShadow: '0 2px 4px rgba(0,0,0,0.5)' }}>{completedCount}</span>
          </div>
        </div>

        <div className="glass-panel glass-panel-interactive" style={{ display: 'flex', alignItems: 'center', gap: '1.1rem', padding: '1.25rem' }}>
          <div style={{ padding: '0.9rem', borderRadius: '14px', background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.3) 0%, rgba(37, 99, 235, 0.3) 100%)', color: '#60a5fa', boxShadow: '0 6px 16px rgba(59,130,246,0.25), inset 0 1px 1px rgba(255,255,255,0.4)', border: '1px solid rgba(96,165,250,0.4)' }}>
            <ShieldCheck size={24} style={{ filter: 'drop-shadow(0 0 4px rgba(96,165,250,0.5))' }} />
          </div>
          <div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 800, letterSpacing: '0.05em' }}>Approval Rate</span>
            <span style={{ fontSize: '1.6rem', fontWeight: 800, color: '#fff', display: 'block', textShadow: '0 2px 4px rgba(0,0,0,0.5)' }}>100%</span>
          </div>
        </div>
      </div>

      {/* Main Grid: Active Executions & Projects */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '1.5rem' }}>
        {/* Active Coding Tasks */}
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <PlayCircle size={20} color="var(--accent-cyan)" style={{ filter: 'drop-shadow(0 0 6px var(--accent-cyan-glow))' }} /> Active Coding Tasks ({tasks.length})
            </h3>
            <button
              onClick={() => navigate('task_history')}
              style={{ background: 'transparent', border: 'none', color: 'var(--accent-cyan)', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.3rem' }}
            >
              View Full History <ArrowRight size={14} />
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
            {tasks.map((task) => (
              <div
                key={task.id}
                onClick={() => {
                  if (task.last_run_id) {
                    useAgentExecutionStore.getState().setActiveExecutionByRunId(task.last_run_id);
                  }
                  navigate('agent_execution', { taskId: task.id, runId: task.last_run_id });
                }}
                style={{
                  padding: '1.1rem 1.25rem',
                  borderRadius: '14px',
                  background: 'rgba(5, 9, 18, 0.75)',
                  border: '1px solid var(--glass-border)',
                  boxShadow: 'var(--skeuo-shadow-raised)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  transition: 'all 0.2s ease',
                }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', maxWidth: '70%' }}>
                  <span style={{ fontSize: '0.96rem', fontWeight: 700, color: 'var(--text-main)' }}>
                    {task.title}
                  </span>
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Project: <strong style={{ color: 'var(--accent-cyan)' }}>{task.project_name || task.project_id}</strong> • Runtime: {task.language_runtime}
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                  <AgentStateBadge state={task.status} size="sm" />
                  <ArrowRight size={18} color="var(--text-muted)" />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Recent Projects Side List */}
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 800, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '0.55rem' }}>
              <Folder size={18} color="var(--accent-purple)" style={{ filter: 'drop-shadow(0 0 6px var(--accent-purple-glow))' }} /> Workspaces
            </h3>
            <button
              onClick={() => navigate('projects')}
              style={{ background: 'transparent', border: 'none', color: 'var(--accent-cyan)', cursor: 'pointer', fontSize: '0.82rem', fontWeight: 700 }}
            >
              All Projects
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
            {projects.map((proj) => (
              <div
                key={proj.id}
                onClick={() => navigate('project_details', { projectId: proj.id })}
                style={{
                  padding: '0.95rem 1rem',
                  borderRadius: '12px',
                  background: 'rgba(5, 9, 18, 0.75)',
                  border: '1px solid var(--glass-border)',
                  boxShadow: 'var(--skeuo-shadow-raised)',
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.35rem',
                  transition: 'all 0.2s ease',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: '0.92rem', fontWeight: 700, color: 'var(--text-main)' }}>
                    {proj.name}
                  </span>
                  <span style={{ fontSize: '0.7rem', background: 'linear-gradient(135deg, rgba(157, 78, 221, 0.3) 0%, rgba(123, 44, 191, 0.3) 100%)', color: '#c77dff', border: '1px solid rgba(199,125,255,0.4)', padding: '0.15rem 0.55rem', borderRadius: '10px', fontWeight: 700, boxShadow: '0 2px 6px rgba(0,0,0,0.3)' }}>
                    {proj.language}
                  </span>
                </div>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden', lineHeight: 1.4 }}>
                  {proj.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
