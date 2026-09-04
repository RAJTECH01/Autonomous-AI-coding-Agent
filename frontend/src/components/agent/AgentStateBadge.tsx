import React from 'react';
import { AgentState } from '../../types/agent';
import { Play, CheckCircle2, AlertCircle, PauseCircle, XCircle, RefreshCw } from 'lucide-react';

interface AgentStateBadgeProps {
  state: AgentState;
  size?: 'sm' | 'md' | 'lg';
}

export const AgentStateBadge: React.FC<AgentStateBadgeProps> = ({ state, size = 'md' }) => {
  const getBadgeStyle = () => {
    switch (state) {
      case 'COMPLETED':
        return {
          bg: 'linear-gradient(135deg, rgba(16, 185, 129, 0.25) 0%, rgba(5, 150, 105, 0.25) 100%)',
          border: 'rgba(52, 211, 153, 0.4)',
          text: '#34d399',
          glow: 'rgba(16, 185, 129, 0.3)',
          icon: <CheckCircle2 size={16} />
        };
      case 'FAILED':
        return {
          bg: 'linear-gradient(135deg, rgba(244, 63, 94, 0.25) 0%, rgba(185, 28, 28, 0.25) 100%)',
          border: 'rgba(251, 113, 133, 0.4)',
          text: '#fb7185',
          glow: 'rgba(244, 63, 94, 0.3)',
          icon: <AlertCircle size={16} />
        };
      case 'CANCELLED':
        return {
          bg: 'linear-gradient(135deg, rgba(148, 163, 184, 0.2) 0%, rgba(71, 85, 105, 0.2) 100%)',
          border: 'rgba(148, 163, 184, 0.3)',
          text: 'var(--text-muted)',
          glow: 'transparent',
          icon: <XCircle size={16} />
        };
      case 'AWAITING_APPROVAL':
        return {
          bg: 'linear-gradient(135deg, rgba(245, 158, 11, 0.25) 0%, rgba(217, 119, 6, 0.25) 100%)',
          border: 'rgba(251, 191, 36, 0.4)',
          text: '#fbbf24',
          glow: 'rgba(245, 158, 11, 0.3)',
          icon: <PauseCircle size={16} />
        };
      case 'TESTING':
      case 'DEBUGGING':
      case 'REVIEWING':
        return {
          bg: 'linear-gradient(135deg, rgba(157, 78, 221, 0.25) 0%, rgba(123, 44, 191, 0.25) 100%)',
          border: 'rgba(199, 125, 255, 0.4)',
          text: '#c77dff',
          glow: 'rgba(157, 78, 221, 0.3)',
          icon: <RefreshCw size={16} className="spin-icon" />
        };
      default:
        return {
          bg: 'linear-gradient(135deg, rgba(0, 242, 254, 0.25) 0%, rgba(59, 130, 246, 0.25) 100%)',
          border: 'rgba(0, 242, 254, 0.4)',
          text: 'var(--accent-cyan)',
          glow: 'rgba(0, 242, 254, 0.3)',
          icon: <Play size={16} />
        };
    }
  };

  const style = getBadgeStyle();
  const padding = size === 'sm' ? '0.25rem 0.6rem' : size === 'lg' ? '0.55rem 1.35rem' : '0.4rem 1rem';
  const fontSize = size === 'sm' ? '0.72rem' : size === 'lg' ? '0.95rem' : '0.82rem';

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.5rem',
        padding,
        borderRadius: '24px',
        background: style.bg,
        border: `1px solid ${style.border}`,
        color: style.text,
        fontSize,
        fontWeight: 800,
        letterSpacing: '0.04em',
        textTransform: 'uppercase',
        boxShadow: `0 6px 16px ${style.glow}, inset 0 1px 1px rgba(255, 255, 255, 0.35), inset 0 -1px 2px rgba(0,0,0,0.4)`,
        backdropFilter: 'blur(10px)',
      }}
    >
      <span style={{ filter: `drop-shadow(0 0 6px ${style.text})` }}>{style.icon}</span>
      {state.replace('_', ' ')}
      <style>{`
        .spin-icon {
          animation: spin 2s linear infinite;
        }
      `}</style>
    </span>
  );
};
