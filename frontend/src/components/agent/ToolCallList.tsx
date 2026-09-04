import React from 'react';
import { ToolCallItem } from '../../types/agent';
import { Wrench, CheckCircle2, XCircle, Clock } from 'lucide-react';

interface ToolCallListProps {
  toolCalls: ToolCallItem[];
}

export const ToolCallList: React.FC<ToolCallListProps> = ({ toolCalls }) => {
  if (toolCalls.length === 0) {
    return (
      <div className="glass-panel" style={{ color: 'var(--text-muted)', fontSize: '0.95rem', padding: '2rem', textAlign: 'center' }}>
        No tool calls executed yet.
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      {toolCalls.map((tc, idx) => (
        <div
          key={tc.id || idx}
          className="glass-panel"
          style={{
            borderLeft: `4px solid ${
              tc.status === 'success'
                ? '#34d399'
                : tc.status === 'failed'
                ? '#fb7185'
                : 'var(--accent-cyan)'
            }`,
            padding: '1.1rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontFamily: 'var(--font-mono)', fontWeight: 800, color: 'var(--accent-cyan)', fontSize: '0.92rem' }}>
              <Wrench size={16} style={{ filter: 'drop-shadow(0 0 6px var(--accent-cyan-glow))' }} />
              <span>{tc.tool_name}</span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem', fontSize: '0.8rem' }}>
              {tc.execution_duration_ms !== undefined && (
                <span style={{ color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.3rem', background: 'rgba(255,255,255,0.06)', padding: '0.15rem 0.5rem', borderRadius: '8px', border: '1px solid var(--glass-border)' }}>
                  <Clock size={13} /> {tc.execution_duration_ms} ms
                </span>
              )}

              <span
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  fontWeight: 800,
                  fontSize: '0.72rem',
                  textTransform: 'uppercase',
                  padding: '0.2rem 0.6rem',
                  borderRadius: '12px',
                  background:
                    tc.status === 'success'
                      ? 'linear-gradient(135deg, rgba(16, 185, 129, 0.3) 0%, rgba(5, 150, 105, 0.3) 100%)'
                      : tc.status === 'failed'
                      ? 'linear-gradient(135deg, rgba(244, 63, 94, 0.3) 0%, rgba(225, 29, 72, 0.3) 100%)'
                      : 'linear-gradient(135deg, rgba(0, 242, 254, 0.3) 0%, rgba(59, 130, 246, 0.3) 100%)',
                  color:
                    tc.status === 'success'
                      ? '#34d399'
                      : tc.status === 'failed'
                      ? '#fb7185'
                      : 'var(--accent-cyan)',
                  border:
                    tc.status === 'success'
                      ? '1px solid rgba(52,211,153,0.4)'
                      : tc.status === 'failed'
                      ? '1px solid rgba(251,113,133,0.4)'
                      : '1px solid rgba(0,242,254,0.4)',
                  boxShadow: '0 2px 6px rgba(0,0,0,0.3)',
                }}
              >
                {tc.status === 'success' ? (
                  <CheckCircle2 size={14} />
                ) : tc.status === 'failed' ? (
                  <XCircle size={14} />
                ) : null}
                {tc.status}
              </span>
            </div>
          </div>

          <div className="skeuo-inset" style={{ padding: '0.75rem 0.9rem', marginBottom: '0.65rem' }}>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.3rem', fontWeight: 700, textTransform: 'uppercase' }}>
              Input Arguments:
            </span>
            <pre style={{ margin: 0, fontSize: '0.82rem', fontFamily: 'var(--font-mono)', color: 'var(--text-main)', whiteSpace: 'pre-wrap' }}>
              {JSON.stringify(tc.tool_input, null, 2)}
            </pre>
          </div>

          {(tc.output || tc.error) && (
            <div className="skeuo-inset" style={{ padding: '0.75rem 0.9rem', borderColor: tc.error ? 'rgba(244,63,94,0.35)' : 'rgba(255,255,255,0.06)' }}>
              <span style={{ fontSize: '0.72rem', color: tc.error ? '#fb7185' : '#34d399', display: 'block', marginBottom: '0.3rem', fontWeight: 700, textTransform: 'uppercase' }}>
                {tc.error ? 'Execution Error:' : 'Result Output:'}
              </span>
              <pre style={{ margin: 0, fontSize: '0.82rem', fontFamily: 'var(--font-mono)', color: tc.error ? '#fb7185' : '#a7f3d0', whiteSpace: 'pre-wrap', maxHeight: '160px', overflowY: 'auto' }}>
                {tc.error || tc.output}
              </pre>
            </div>
          )}
        </div>
      ))}
    </div>
  );
};
