import React, { useState } from 'react';
import { useAgentExecutionStore } from '../store/useAgentExecutionStore';
import { useNavigationStore } from '../store/useNavigationStore';
import { AgentStateBadge } from '../components/agent/AgentStateBadge';
import { History, Search, RefreshCw, ArrowRight } from 'lucide-react';

export const TaskHistoryPage: React.FC = () => {
  const { tasks, retryTask } = useAgentExecutionStore();
  const { navigate } = useNavigationStore();
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState<string>('ALL');

  const filteredTasks = tasks.filter((t) => {
    const matchesSearch =
      t.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      t.requirement_prompt.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStatus = filterStatus === 'ALL' || t.status === filterStatus;
    return matchesSearch && matchesStatus;
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <History size={26} color="var(--accent-cyan)" style={{ filter: 'drop-shadow(0 0 6px var(--accent-cyan-glow))' }} /> Autonomous Task Execution History
          </h2>
          <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            Complete audit trail of created coding tasks, statuses, and execution runs.
          </p>
        </div>
      </div>

      {/* Filter Bar */}
      <div style={{ display: 'flex', gap: '1.25rem', alignItems: 'center' }}>
        <div style={{ position: 'relative', flex: 1 }}>
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Filter tasks by title or requirement..."
            style={{ paddingLeft: '2.75rem' }}
          />
          <Search size={18} color="var(--text-dim)" style={{ position: 'absolute', left: '0.95rem', top: '50%', transform: 'translateY(-50%)' }} />
        </div>

        <div style={{ width: '220px' }}>
          <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
            <option value="ALL">All Statuses</option>
            <option value="COMPLETED">Completed</option>
            <option value="IMPLEMENTING">Implementing</option>
            <option value="AWAITING_APPROVAL">Awaiting Approval</option>
            <option value="FAILED">Failed</option>
            <option value="CANCELLED">Cancelled</option>
          </select>
        </div>
      </div>

      {/* Tasks Table */}
      <div className="glass-panel" style={{ padding: 0, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.88rem' }}>
          <thead>
            <tr style={{ background: 'rgba(5, 9, 18, 0.8)', borderBottom: '1px solid var(--glass-border)', color: 'var(--text-muted)', fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              <th style={{ padding: '1rem 1.35rem' }}>Task Title & Requirement</th>
              <th style={{ padding: '1rem 1.35rem' }}>Runtime</th>
              <th style={{ padding: '1rem 1.35rem' }}>Status</th>
              <th style={{ padding: '1rem 1.35rem' }}>Runs</th>
              <th style={{ padding: '1rem 1.35rem' }}>Created At</th>
              <th style={{ padding: '1rem 1.35rem', textAlign: 'right' }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {filteredTasks.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ padding: '2.5rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.95rem' }}>
                  No matching tasks found in history.
                </td>
              </tr>
            ) : (
              filteredTasks.map((t) => (
                <tr key={t.id} style={{ borderBottom: '1px solid var(--glass-border)', transition: 'all 0.2s ease' }}>
                  <td style={{ padding: '1.1rem 1.35rem', maxWidth: '320px' }}>
                    <span style={{ fontWeight: 700, color: 'var(--text-main)', display: 'block', marginBottom: '0.25rem', fontSize: '0.92rem' }}>
                      {t.title}
                    </span>
                    <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: '-webkit-box', WebkitLineClamp: 1, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                      {t.requirement_prompt}
                    </span>
                  </td>

                  <td style={{ padding: '1.1rem 1.35rem', color: '#c77dff', fontWeight: 700 }}>
                    {t.language_runtime}
                  </td>

                  <td style={{ padding: '1.1rem 1.35rem' }}>
                    <AgentStateBadge state={t.status} size="sm" />
                  </td>

                  <td style={{ padding: '1.1rem 1.35rem', fontWeight: 800, color: '#fff' }}>
                    {t.runs_count}
                  </td>

                  <td style={{ padding: '1.1rem 1.35rem', color: 'var(--text-muted)', fontSize: '0.82rem' }}>
                    {new Date(t.created_at).toLocaleString()}
                  </td>

                  <td style={{ padding: '1.1rem 1.35rem', textAlign: 'right' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '0.6rem' }}>
                      <button
                        onClick={() => {
                          if (t.last_run_id) {
                            useAgentExecutionStore.getState().setActiveExecutionByRunId(t.last_run_id);
                          }
                          navigate('agent_execution', { taskId: t.id, runId: t.last_run_id });
                        }}
                        className="btn"
                        style={{ padding: '0.4rem 0.85rem', fontSize: '0.78rem' }}
                      >
                        Inspect <ArrowRight size={13} />
                      </button>

                      <button
                        onClick={() => retryTask(t.id)}
                        className="btn btn-secondary"
                        style={{ padding: '0.4rem 0.75rem', fontSize: '0.78rem' }}
                      >
                        <RefreshCw size={13} /> Retry
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
