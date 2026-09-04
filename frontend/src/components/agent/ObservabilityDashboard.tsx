import React from 'react';
import { Activity, Cpu, DollarSign, Clock, ShieldCheck, Zap, Terminal, Server, CheckCircle2, XCircle } from 'lucide-react';
import { DashboardMetricsSummary, BackgroundJob } from '../../types/observability';

interface ObservabilityDashboardProps {
  metrics?: DashboardMetricsSummary;
  jobs?: BackgroundJob[];
}

export const ObservabilityDashboard: React.FC<ObservabilityDashboardProps> = ({
  metrics = {
    system_uptime_seconds: 14280.5,
    tasks: {
      started: 42,
      completed: 39,
      failed: 3,
      average_execution_time_seconds: 48.6,
      average_iterations: 3.4,
    },
    tools: {
      total_calls: 318,
      breakdown: {
        read_file: { total: 112, success: 112, failed: 0 },
        write_file: { total: 84, success: 84, failed: 0 },
        run_tests: { total: 46, success: 38, failed: 8 },
        execute_command: { total: 42, success: 42, failed: 0 },
        get_git_status: { total: 24, success: 24, failed: 0 },
        create_git_commit: { total: 10, success: 10, failed: 0 },
      },
      test_failures: 8,
      retry_count: 5,
    },
    ai_telemetry: {
      prompt_tokens: 184500,
      completion_tokens: 42300,
      total_tokens: 226800,
      estimated_cost_usd: 1.1880,
      model_latencies_seconds: {
        'anthropic:claude-3-5-sonnet-20241022': 2.45,
        'openai:gpt-4o': 1.82,
      },
    },
    infrastructure: {
      sandbox_failures: { container_error: 0, memory_limit: 0 },
      total_sandbox_failures: 0,
    },
  },
  jobs = [
    {
      job_id: 'task-174',
      name: 'Frontend Dev Server',
      job_type: 'daemon_process',
      status: 'running',
      start_time: new Date().toISOString(),
      duration_seconds: 14200.0,
      command: 'npm run dev',
      last_log_snippet: 'Vite v5.4.21 ready in 420 ms. Local: http://localhost:5173/',
    },
    {
      job_id: 'job-agent-worker-1',
      name: 'Agent Execution State Machine',
      job_type: 'agent_run',
      status: 'running',
      start_time: new Date().toISOString(),
      duration_seconds: 145.2,
      command: 'state_machine.run_autonomous_loop()',
      last_log_snippet: 'Step 4: Executing code implementation tools and validating tests.',
    },
  ],
}) => {
  const successRate = metrics.tasks.started > 0
    ? Math.round((metrics.tasks.completed / metrics.tasks.started) * 100)
    : 100;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Top Banner Header */}
      <div className="glass-panel" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '1.25rem 1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem' }}>
          <div style={{
            background: 'linear-gradient(135deg, rgba(168,85,247,0.3) 0%, rgba(126,34,206,0.3) 100%)',
            padding: '0.7rem',
            borderRadius: '14px',
            border: '1px solid rgba(192,132,252,0.4)',
            boxShadow: 'var(--skeuo-shadow-raised)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <Activity size={26} color="#c084fc" />
          </div>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
              <h2 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#ffffff', margin: 0 }}>
                Production Observability & Telemetry Cockpit
              </h2>
              <span style={{
                fontSize: '0.75rem',
                padding: '0.2rem 0.65rem',
                borderRadius: '12px',
                background: 'linear-gradient(135deg, rgba(52, 211, 153, 0.25) 0%, rgba(16, 185, 129, 0.25) 100%)',
                color: '#34d399',
                border: '1px solid rgba(52, 211, 153, 0.4)',
                fontWeight: 800,
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem'
              }}>
                <ShieldCheck size={13} /> SYSTEM READY & HEALTHY
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem', marginTop: '0.35rem', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
              <span>Uptime: <strong style={{ color: '#ffffff' }}>{(metrics.system_uptime_seconds / 3600).toFixed(1)} hrs</strong></span>
              <span>•</span>
              <span>Overall Success Rate: <strong style={{ color: '#34d399' }}>{successRate}%</strong></span>
              <span>•</span>
              <span>Active Daemon Jobs: <strong style={{ color: '#c084fc' }}>{jobs.filter(j => j.status === 'running').length} Active</strong></span>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
          <div className="skeuo-inset" style={{ padding: '0.6rem 1rem', borderRadius: '10px', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <DollarSign size={18} color="#34d399" />
            <div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 700 }}>Est. AI Cost (USD)</div>
              <div style={{ fontSize: '1rem', fontWeight: 800, color: '#34d399' }}>${metrics.ai_telemetry.estimated_cost_usd.toFixed(4)}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Grid Row 1: Task Execution & Performance Metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1.25rem' }}>
        <div className="glass-panel" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '0.78rem', fontWeight: 800, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Tasks Executed</span>
            <Zap size={18} color="#c084fc" />
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 900, color: '#ffffff' }}>{metrics.tasks.started}</div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            Completed: <span style={{ color: '#34d399', fontWeight: 700 }}>{metrics.tasks.completed}</span> | Failed: <span style={{ color: '#fb7185', fontWeight: 700 }}>{metrics.tasks.failed}</span>
          </div>
        </div>

        <div className="glass-panel" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '0.78rem', fontWeight: 800, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Avg Execution Time</span>
            <Clock size={18} color="#c084fc" />
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 900, color: '#ffffff' }}>{metrics.tasks.average_execution_time_seconds}s</div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            Average Iterations: <span style={{ color: '#c084fc', fontWeight: 700 }}>{metrics.tasks.average_iterations} steps</span>
          </div>
        </div>

        <div className="glass-panel" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '0.78rem', fontWeight: 800, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Tool Call Volume</span>
            <Terminal size={18} color="#c084fc" />
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 900, color: '#ffffff' }}>{metrics.tools.total_calls}</div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            Test Failures: <span style={{ color: '#fb7185', fontWeight: 700 }}>{metrics.tools.test_failures}</span> | Retries: <span style={{ color: '#fbbf24', fontWeight: 700 }}>{metrics.tools.retry_count}</span>
          </div>
        </div>

        <div className="glass-panel" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '0.78rem', fontWeight: 800, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Total LLM Tokens</span>
            <Cpu size={18} color="#c084fc" />
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 900, color: '#ffffff' }}>{metrics.ai_telemetry.total_tokens.toLocaleString()}</div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            Prompt: <span style={{ color: '#ffffff' }}>{(metrics.ai_telemetry.prompt_tokens / 1000).toFixed(1)}k</span> | Completion: <span style={{ color: '#ffffff' }}>{(metrics.ai_telemetry.completion_tokens / 1000).toFixed(1)}k</span>
          </div>
        </div>
      </div>

      {/* Grid Row 2: Model Latencies & Tool Call Breakdown */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
        {/* Model Latencies & Token Telemetry */}
        <div className="glass-panel" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <h3 style={{ fontSize: '0.95rem', fontWeight: 800, color: '#ffffff', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Cpu size={16} color="#c084fc" /> LLM Model Latency & Token Usage
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {Object.entries(metrics.ai_telemetry.model_latencies_seconds).map(([modelKey, lat], idx) => (
              <div
                key={idx}
                style={{
                  padding: '0.85rem 1rem',
                  borderRadius: '10px',
                  background: 'rgba(3, 1, 6, 0.8)',
                  border: '1px solid var(--glass-border)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.15rem' }}>
                  <span style={{ fontSize: '0.85rem', fontWeight: 800, color: '#ffffff' }}>{modelKey}</span>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Average Response Latency</span>
                </div>
                <div style={{ fontSize: '1.1rem', fontWeight: 900, color: '#c084fc' }}>
                  {lat}s
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Tool Call Distribution */}
        <div className="glass-panel" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <h3 style={{ fontSize: '0.95rem', fontWeight: 800, color: '#ffffff', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Terminal size={16} color="#c084fc" /> Tool Execution Distribution
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {Object.entries(metrics.tools.breakdown).map(([tName, tData], idx) => (
              <div
                key={idx}
                style={{
                  padding: '0.65rem 0.9rem',
                  borderRadius: '8px',
                  background: 'rgba(3, 1, 6, 0.75)',
                  border: '1px solid var(--glass-border)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <span style={{ fontSize: '0.84rem', fontWeight: 700, color: '#ffffff', fontFamily: 'var(--font-mono)' }}>
                  {tName}
                </span>

                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', fontSize: '0.78rem' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Total: <strong style={{ color: '#ffffff' }}>{tData.total}</strong></span>
                  <span style={{ color: '#34d399', fontWeight: 700 }}>{tData.success} ok</span>
                  {tData.failed > 0 && <span style={{ color: '#fb7185', fontWeight: 700 }}>{tData.failed} err</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Grid Row 3: Background Job Monitoring Table */}
      <div className="glass-panel" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <h3 style={{ fontSize: '0.95rem', fontWeight: 800, color: '#ffffff', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Server size={16} color="#c084fc" /> Background Job & Worker Telemetry ({jobs.length})
        </h3>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--glass-border)', color: 'var(--text-muted)', textAlign: 'left' }}>
                <th style={{ padding: '0.75rem', textTransform: 'uppercase', fontSize: '0.75rem' }}>Job ID</th>
                <th style={{ padding: '0.75rem', textTransform: 'uppercase', fontSize: '0.75rem' }}>Name / Type</th>
                <th style={{ padding: '0.75rem', textTransform: 'uppercase', fontSize: '0.75rem' }}>Command</th>
                <th style={{ padding: '0.75rem', textTransform: 'uppercase', fontSize: '0.75rem' }}>Status</th>
                <th style={{ padding: '0.75rem', textTransform: 'uppercase', fontSize: '0.75rem' }}>Runtime</th>
                <th style={{ padding: '0.75rem', textTransform: 'uppercase', fontSize: '0.75rem' }}>Latest Log Output</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j, idx) => (
                <tr key={idx} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                  <td style={{ padding: '0.75rem', fontFamily: 'var(--font-mono)', color: '#c084fc', fontWeight: 700 }}>
                    {j.job_id}
                  </td>
                  <td style={{ padding: '0.75rem', color: '#ffffff', fontWeight: 700 }}>
                    {j.name}
                  </td>
                  <td style={{ padding: '0.75rem', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                    {j.command || 'N/A'}
                  </td>
                  <td style={{ padding: '0.75rem' }}>
                    {j.status === 'running' ? (
                      <span style={{ color: '#34d399', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                        <CheckCircle2 size={14} /> RUNNING
                      </span>
                    ) : (
                      <span style={{ color: '#fb7185', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                        <XCircle size={14} /> {j.status.toUpperCase()}
                      </span>
                    )}
                  </td>
                  <td style={{ padding: '0.75rem', color: 'var(--text-muted)' }}>
                    {j.duration_seconds}s
                  </td>
                  <td style={{ padding: '0.75rem', fontFamily: 'var(--font-mono)', color: '#e2e8f0', fontSize: '0.75rem', maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {j.last_log_snippet || 'No output recorded'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
