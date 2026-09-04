import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface ErrorAlertProps {
  message: string;
  onRetry?: () => void;
}

export const ErrorAlert: React.FC<ErrorAlertProps> = ({ message, onRetry }) => {
  return (
    <div
      style={{
        background: 'linear-gradient(135deg, rgba(244, 63, 94, 0.2) 0%, rgba(185, 28, 28, 0.15) 100%)',
        border: '1px solid rgba(251, 113, 133, 0.35)',
        borderRadius: '14px',
        padding: '1.1rem 1.4rem',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        color: '#fca5a5',
        fontSize: '0.9rem',
        boxShadow: '0 8px 24px -4px rgba(244, 63, 94, 0.25), inset 0 1px 1px rgba(255, 255, 255, 0.3)',
        backdropFilter: 'blur(16px)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <AlertTriangle size={20} color="#fb7185" style={{ filter: 'drop-shadow(0 0 6px rgba(244,63,94,0.6))' }} />
        <span style={{ fontWeight: 600 }}>{message}</span>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="btn btn-danger"
          style={{
            padding: '0.45rem 0.9rem',
            fontSize: '0.82rem',
            borderRadius: '10px',
          }}
        >
          <RefreshCw size={14} /> Retry
        </button>
      )}
    </div>
  );
};
