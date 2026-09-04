import React from 'react';
import { FolderOpen, Plus } from 'lucide-react';

interface EmptyStateProps {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title,
  description,
  actionLabel,
  onAction,
}) => {
  return (
    <div
      className="glass-panel"
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '4rem 2rem',
        textAlign: 'center',
        border: '1px dashed var(--glass-border-light)',
      }}
    >
      <div
        style={{
          width: '64px',
          height: '64px',
          borderRadius: '50%',
          background: 'linear-gradient(135deg, rgba(0, 242, 254, 0.2) 0%, rgba(157, 78, 221, 0.2) 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: '1.25rem',
          color: 'var(--accent-cyan)',
          border: '1px solid rgba(0, 242, 254, 0.3)',
          boxShadow: 'var(--skeuo-shadow-raised)',
        }}
      >
        <FolderOpen size={30} style={{ filter: 'drop-shadow(0 0 8px var(--accent-cyan-glow))' }} />
      </div>
      <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--text-main)', marginBottom: '0.5rem' }}>
        {title}
      </h3>
      <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', maxWidth: '420px', marginBottom: '1.75rem', lineHeight: 1.5 }}>
        {description}
      </p>
      {actionLabel && onAction && (
        <button className="btn" onClick={onAction}>
          <Plus size={18} />
          {actionLabel}
        </button>
      )}
    </div>
  );
};
