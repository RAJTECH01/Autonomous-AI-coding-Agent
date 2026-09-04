import React, { useEffect, useRef } from 'react';
import { Terminal, Download } from 'lucide-react';

interface LogViewerProps {
  logs: string[];
}

export const LogViewer: React.FC<LogViewerProps> = ({ logs }) => {
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const handleDownloadLogs = () => {
    const text = logs.join('\n');
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `agent_run_logs_${Date.now()}.log`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="glass-panel" style={{ padding: '1.25rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.85rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontSize: '0.92rem', fontWeight: 700, color: 'var(--text-main)' }}>
          <Terminal size={18} color="var(--accent-cyan)" style={{ filter: 'drop-shadow(0 0 6px var(--accent-cyan-glow))' }} />
          <span>Live Agent Execution Logs</span>
          <span style={{ fontSize: '0.75rem', background: 'rgba(0,242,254,0.15)', color: 'var(--accent-cyan)', padding: '0.15rem 0.5rem', borderRadius: '10px', border: '1px solid rgba(0,242,254,0.3)' }}>
            {logs.length} lines
          </span>
        </div>

        <button
          onClick={handleDownloadLogs}
          className="btn btn-secondary"
          style={{
            padding: '0.35rem 0.75rem',
            fontSize: '0.78rem',
            borderRadius: '8px',
          }}
        >
          <Download size={14} /> Export Logs
        </button>
      </div>

      <div className="skeuo-inset log-stream">
        {logs.length === 0 ? (
          <span style={{ color: 'var(--text-dim)' }}>Waiting for log output...</span>
        ) : (
          logs.map((log, index) => (
            <div key={index} style={{ marginBottom: '0.25rem', lineHeight: 1.4 }}>
              {log}
            </div>
          ))
        )}
        <div ref={logEndRef} />
      </div>
    </div>
  );
};
