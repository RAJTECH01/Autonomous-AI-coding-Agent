import React from 'react';
import { ReviewResultData, ReviewSeverity } from '../../types/agent';
import { ShieldCheck, ShieldAlert, FileCode, CheckCircle2 } from 'lucide-react';

interface ReviewFindingsViewerProps {
  review?: ReviewResultData;
}

export const ReviewFindingsViewer: React.FC<ReviewFindingsViewerProps> = ({ review }) => {
  if (!review) {
    return (
      <div className="glass-panel" style={{ color: 'var(--text-muted)', fontSize: '0.95rem', padding: '2rem', textAlign: 'center' }}>
        No final code review completed yet.
      </div>
    );
  }

  const getSeverityBadge = (severity: ReviewSeverity) => {
    switch (severity) {
      case 'CRITICAL':
        return { bg: 'linear-gradient(135deg, rgba(244, 63, 94, 0.3) 0%, rgba(185, 28, 28, 0.3) 100%)', color: '#fb7185', border: 'rgba(251, 113, 133, 0.4)' };
      case 'HIGH':
        return { bg: 'linear-gradient(135deg, rgba(245, 158, 11, 0.3) 0%, rgba(217, 119, 6, 0.3) 100%)', color: '#fbbf24', border: 'rgba(251, 191, 36, 0.4)' };
      case 'MEDIUM':
        return { bg: 'linear-gradient(135deg, rgba(234, 179, 8, 0.3) 0%, rgba(161, 98, 7, 0.3) 100%)', color: '#facc15', border: 'rgba(250, 204, 21, 0.4)' };
      case 'LOW':
        return { bg: 'linear-gradient(135deg, rgba(59, 130, 246, 0.3) 0%, rgba(29, 78, 216, 0.3) 100%)', color: '#60a5fa', border: 'rgba(96, 165, 250, 0.4)' };
      default:
        return { bg: 'rgba(148, 163, 184, 0.2)', color: 'var(--text-muted)', border: 'rgba(148, 163, 184, 0.3)' };
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div
        className="glass-panel"
        style={{
          borderLeft: `4px solid ${review.passed ? '#34d399' : '#fb7185'}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
          {review.passed ? (
            <ShieldCheck size={32} color="#34d399" style={{ filter: 'drop-shadow(0 0 8px rgba(52,211,153,0.5))' }} />
          ) : (
            <ShieldAlert size={32} color="#fb7185" style={{ filter: 'drop-shadow(0 0 8px rgba(244,63,94,0.5))' }} />
          )}
          <div>
            <h4 style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--text-main)' }}>
              {review.passed ? 'Code Review Approved' : 'Code Review Rejected (Blocking Findings Found)'}
            </h4>
            <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginTop: '0.25rem', lineHeight: 1.5 }}>
              {review.summary}
            </p>
          </div>
        </div>

        <div style={{ textAlign: 'right' }}>
          <span style={{ fontSize: '1.4rem', fontWeight: 800, color: review.blocking_findings_count > 0 ? '#fb7185' : '#34d399', textShadow: '0 0 10px rgba(0,0,0,0.5)' }}>
            {review.blocking_findings_count}
          </span>
          <span style={{ display: 'block', fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.05em' }}>
            Blocking Findings
          </span>
        </div>
      </div>

      <div className="glass-panel">
        <h4 style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--text-main)', marginBottom: '1.25rem' }}>
          Review Findings ({review.findings.length})
        </h4>

        {review.findings.length === 0 ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', color: '#34d399', fontSize: '0.92rem', fontWeight: 600, padding: '1.2rem', background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.2) 0%, rgba(5, 150, 105, 0.15) 100%)', border: '1px solid rgba(52, 211, 153, 0.3)', borderRadius: '12px', boxShadow: '0 4px 12px rgba(16, 185, 129, 0.15)' }}>
            <CheckCircle2 size={20} /> Zero issues detected across all 12 review categories.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {review.findings.map((item, idx) => {
              const sev = getSeverityBadge(item.severity);
              return (
                <div
                  key={idx}
                  style={{
                    background: 'rgba(5, 9, 18, 0.75)',
                    border: '1px solid var(--glass-border)',
                    borderRadius: '12px',
                    padding: '1.1rem',
                    boxShadow: 'var(--skeuo-shadow-raised)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.6rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.7rem' }}>
                      <span style={{ fontSize: '0.7rem', padding: '0.2rem 0.6rem', borderRadius: '12px', background: sev.bg, color: sev.color, border: `1px solid ${sev.border}`, fontWeight: 800, boxShadow: '0 2px 6px rgba(0,0,0,0.3)' }}>
                        {item.severity}
                      </span>
                      <span style={{ fontSize: '0.98rem', fontWeight: 800, color: 'var(--text-main)' }}>
                        {item.finding}
                      </span>
                    </div>
                    <span style={{ fontSize: '0.75rem', color: 'var(--accent-cyan)', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.04em' }}>
                      {item.category}
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.82rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: '0.6rem' }}>
                    <FileCode size={15} color="var(--accent-purple)" />
                    <span>Affected File: {item.affected_file}</span>
                  </div>

                  <p style={{ fontSize: '0.9rem', color: 'var(--text-main)', marginBottom: '0.85rem', lineHeight: '1.5' }}>
                    {item.explanation}
                  </p>

                  <div style={{ background: 'rgba(0, 242, 254, 0.1)', border: '1px solid rgba(0, 242, 254, 0.25)', padding: '0.75rem 0.9rem', borderRadius: '10px', fontSize: '0.88rem' }}>
                    <strong style={{ color: 'var(--accent-cyan)', display: 'block', marginBottom: '0.3rem' }}>Recommended Fix:</strong>
                    <span style={{ color: 'var(--text-main)' }}>{item.recommended_fix}</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
