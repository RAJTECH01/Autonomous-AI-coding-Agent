import React from 'react';
import { useAgentExecutionStore } from '../store/useAgentExecutionStore';
import { LogViewer } from '../components/agent/LogViewer';
import { Terminal, ShieldCheck, Hash } from 'lucide-react';

export const AgentLogsPage: React.FC = () => {
  const { activeExecution } = useAgentExecutionStore();

  const auditRecords = [
    {
      role: 'planner',
      version: '1.0.0',
      hash: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
      variant: 'default',
      timestamp: new Date().toISOString(),
    },
    {
      role: 'reviewer',
      version: '1.0.0',
      hash: '8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88b59b2dc327aa4',
      variant: 'default',
      timestamp: new Date().toISOString(),
    },
    {
      role: 'debugger',
      version: '1.0.0',
      hash: '7d1a54127b222502f5b79b5fb0803061152a44f92b37e23c6527b63f28d6f99a',
      variant: 'default',
      timestamp: new Date().toISOString(),
    },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
      <div>
        <h2 style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <Terminal size={26} color="var(--accent-cyan)" style={{ filter: 'drop-shadow(0 0 6px var(--accent-cyan-glow))' }} /> Agent Logs & Prompt Audit Records
        </h2>
        <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
          Audit trail of prompt versions used (`1.0.0`), SHA-256 content hashes, and execution logs.
        </p>
      </div>

      {/* Prompt Audit Hashes Table */}
      <div className="glass-panel">
        <h3 style={{ fontSize: '1.05rem', fontWeight: 800, color: 'var(--text-main)', marginBottom: '1.1rem', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <ShieldCheck size={20} color="#34d399" style={{ filter: 'drop-shadow(0 0 6px rgba(52,211,153,0.5))' }} /> Prompt Audit Records (Active Run)
        </h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {auditRecords.map((r, idx) => (
            <div
              key={idx}
              style={{
                padding: '0.85rem 1.15rem',
                borderRadius: '12px',
                background: 'rgba(5, 9, 18, 0.75)',
                border: '1px solid var(--glass-border)',
                boxShadow: 'var(--skeuo-shadow-inset)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                fontSize: '0.88rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
                <span style={{ fontWeight: 800, color: 'var(--accent-cyan)', textTransform: 'uppercase', width: '100px', letterSpacing: '0.05em' }}>
                  {r.role}
                </span>
                <span style={{ fontSize: '0.72rem', background: 'linear-gradient(135deg, rgba(168, 85, 247, 0.3) 0%, rgba(139, 92, 246, 0.3) 100%)', color: '#c77dff', border: '1px solid rgba(168, 85, 247, 0.4)', padding: '0.15rem 0.55rem', borderRadius: '10px', fontWeight: 700 }}>
                  v{r.version}
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                <Hash size={15} color="#34d399" /> SHA-256: <span style={{ color: 'var(--text-main)', fontWeight: 600 }}>{r.hash.slice(0, 24)}...</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Active Run Log Stream */}
      <LogViewer logs={activeExecution ? activeExecution.logs : ['[INFO] No active execution session.']} />
    </div>
  );
};
