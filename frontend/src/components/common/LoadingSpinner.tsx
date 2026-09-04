import React from 'react';

interface LoadingSpinnerProps {
  size?: number;
  label?: string;
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({ size = 24, label }) => {
  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.75rem' }}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{ animation: 'spin 0.9s cubic-bezier(0.68, -0.55, 0.27, 1.55) infinite', color: 'var(--accent-cyan)', filter: 'drop-shadow(0 0 8px var(--accent-cyan-glow))' }}
      >
        <circle cx="12" cy="12" r="10" strokeOpacity="0.2" />
        <path d="M12 2a10 10 0 0 1 10 10" />
      </svg>
      {label && <span style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-muted)' }}>{label}</span>}
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};
