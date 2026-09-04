import React from 'react';
import { TestResultsData } from '../../types/agent';
import { CheckCircle2, AlertTriangle, XCircle, HelpCircle } from 'lucide-react';

interface TestResultsViewerProps {
  testResults?: TestResultsData;
}

export const TestResultsViewer: React.FC<TestResultsViewerProps> = ({ testResults }) => {
  if (!testResults) {
    return (
      <div className="glass-panel" style={{ color: 'var(--text-muted)', fontSize: '0.95rem', padding: '2rem', textAlign: 'center' }}>
        No automated test executions recorded yet.
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div
        className="glass-panel"
        style={{
          borderLeft: `4px solid ${testResults.passed ? '#34d399' : '#fb7185'}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
          {testResults.passed ? (
            <CheckCircle2 size={28} color="#34d399" style={{ filter: 'drop-shadow(0 0 8px rgba(52,211,153,0.5))' }} />
          ) : (
            <XCircle size={28} color="#fb7185" style={{ filter: 'drop-shadow(0 0 8px rgba(244,63,94,0.5))' }} />
          )}
          <div>
            <h4 style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--text-main)' }}>
              {testResults.passed ? 'All Test Criteria Passed' : 'Test Failures Detected'}
            </h4>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              Runner: <strong style={{ color: 'var(--accent-cyan)' }}>{testResults.framework}</strong> ({testResults.language}) • Duration: {testResults.duration_ms} ms
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '1.25rem', textAlign: 'center' }}>
          <div style={{ background: 'rgba(5, 9, 18, 0.6)', padding: '0.4rem 0.85rem', borderRadius: '10px', border: '1px solid var(--glass-border)', boxShadow: 'var(--skeuo-shadow-inset)' }}>
            <span style={{ fontSize: '1.3rem', fontWeight: 800, color: '#34d399', display: 'block', textShadow: '0 0 6px rgba(52,211,153,0.4)' }}>
              {testResults.passed_count}
            </span>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 700 }}>Passed</span>
          </div>

          <div style={{ background: 'rgba(5, 9, 18, 0.6)', padding: '0.4rem 0.85rem', borderRadius: '10px', border: '1px solid var(--glass-border)', boxShadow: 'var(--skeuo-shadow-inset)' }}>
            <span style={{ fontSize: '1.3rem', fontWeight: 800, color: testResults.failed_count > 0 ? '#fb7185' : 'var(--text-muted)', display: 'block', textShadow: testResults.failed_count > 0 ? '0 0 6px rgba(244,63,94,0.4)' : 'none' }}>
              {testResults.failed_count}
            </span>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 700 }}>Failed</span>
          </div>

          <div style={{ background: 'rgba(5, 9, 18, 0.6)', padding: '0.4rem 0.85rem', borderRadius: '10px', border: '1px solid var(--glass-border)', boxShadow: 'var(--skeuo-shadow-inset)' }}>
            <span style={{ fontSize: '1.3rem', fontWeight: 800, color: '#fff', display: 'block' }}>
              {testResults.total_tests}
            </span>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 700 }}>Total</span>
          </div>
        </div>
      </div>

      {testResults.failing_tests.length > 0 && (
        <div className="glass-panel">
          <h4 style={{ fontSize: '1rem', fontWeight: 800, color: '#fb7185', marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <AlertTriangle size={20} color="#fb7185" style={{ filter: 'drop-shadow(0 0 6px rgba(244,63,94,0.5))' }} /> Failing Test Cases ({testResults.failing_tests.length})
          </h4>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {testResults.failing_tests.map((ft, idx) => (
              <div
                key={idx}
                style={{
                  background: 'rgba(5, 9, 18, 0.75)',
                  border: '1px solid rgba(244, 63, 94, 0.35)',
                  borderRadius: '12px',
                  padding: '1.1rem',
                  boxShadow: 'var(--skeuo-shadow-raised)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.6rem' }}>
                  <span style={{ fontSize: '0.92rem', fontWeight: 800, color: '#fb7185', fontFamily: 'var(--font-mono)' }}>
                    {ft.test_name}
                  </span>
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                    {ft.file_path}:{ft.line_number || 1}
                  </span>
                </div>

                <p style={{ fontSize: '0.88rem', color: '#fca5a5', marginBottom: '0.85rem', fontWeight: 600 }}>
                  {ft.failure_message}
                </p>

                {ft.likely_cause && (
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem', fontSize: '0.85rem', color: '#fde047', background: 'rgba(245, 158, 11, 0.15)', border: '1px solid rgba(245, 158, 11, 0.3)', padding: '0.65rem 0.85rem', borderRadius: '8px', marginBottom: '0.85rem' }}>
                    <HelpCircle size={16} style={{ flexShrink: 0, marginTop: '2px' }} />
                    <span>Likely Cause: {ft.likely_cause}</span>
                  </div>
                )}

                {ft.stack_trace && (
                  <pre
                    className="skeuo-inset"
                    style={{
                      color: '#fb7185',
                      fontSize: '0.8rem',
                      fontFamily: 'var(--font-mono)',
                      padding: '0.85rem',
                      borderRadius: '8px',
                      margin: 0,
                      overflowX: 'auto',
                    }}
                  >
                    {ft.stack_trace}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
