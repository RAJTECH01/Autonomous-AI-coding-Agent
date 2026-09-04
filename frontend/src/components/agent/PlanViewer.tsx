import React from 'react';
import { AgentPlanData } from '../../types/agent';
import { CheckSquare, FileText, Code2, Terminal } from 'lucide-react';

interface PlanViewerProps {
  plan?: AgentPlanData;
}

export const PlanViewer: React.FC<PlanViewerProps> = ({ plan }) => {
  if (!plan) {
    return (
      <div className="glass-panel" style={{ color: 'var(--text-muted)', fontSize: '0.95rem', padding: '2rem', textAlign: 'center' }}>
        No implementation plan generated yet.
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div className="glass-panel" style={{ borderLeft: '4px solid var(--accent-cyan)' }}>
        <h4 style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--text-main)', marginBottom: '0.6rem', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <FileText size={20} color="var(--accent-cyan)" style={{ filter: 'drop-shadow(0 0 6px var(--accent-cyan-glow))' }} /> Plan Summary
        </h4>
        <p style={{ fontSize: '0.92rem', color: 'var(--text-muted)', lineHeight: '1.6' }}>
          {plan.goals_summary}
        </p>
      </div>

      <div className="glass-panel">
        <h4 style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--text-main)', marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <CheckSquare size={20} color="#34d399" style={{ filter: 'drop-shadow(0 0 6px rgba(52,211,153,0.5))' }} /> Structured Execution Steps ({plan.steps.length})
        </h4>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {plan.steps.map((step) => (
            <div
              key={step.step_number}
              style={{
                padding: '1rem 1.25rem',
                borderRadius: '12px',
                background: 'rgba(5, 9, 18, 0.75)',
                border: '1px solid var(--glass-border)',
                boxShadow: 'var(--skeuo-shadow-raised)',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.65rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '0.88rem', fontWeight: 800, color: 'var(--accent-cyan)', letterSpacing: '0.02em' }}>
                  Step #{step.step_number}
                </span>
                <span
                  style={{
                    fontSize: '0.7rem',
                    padding: '0.2rem 0.6rem',
                    borderRadius: '12px',
                    fontWeight: 800,
                    textTransform: 'uppercase',
                    background: step.action_type === 'create'
                      ? 'linear-gradient(135deg, rgba(16, 185, 129, 0.3) 0%, rgba(5, 150, 105, 0.3) 100%)'
                      : 'linear-gradient(135deg, rgba(0, 242, 254, 0.3) 0%, rgba(59, 130, 246, 0.3) 100%)',
                    color: step.action_type === 'create' ? '#34d399' : 'var(--accent-cyan)',
                    border: step.action_type === 'create' ? '1px solid rgba(52,211,153,0.4)' : '1px solid rgba(0,242,254,0.4)',
                    boxShadow: '0 2px 6px rgba(0,0,0,0.3)',
                  }}
                >
                  {step.action_type}
                </span>
              </div>

              <p style={{ fontSize: '0.92rem', color: 'var(--text-main)', lineHeight: 1.5 }}>{step.description}</p>

              {step.target_files.length > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.82rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                  <Code2 size={15} color="var(--accent-purple)" />
                  <span>Target Files: {step.target_files.join(', ')}</span>
                </div>
              )}

              {step.verification_command && (
                <div className="skeuo-inset" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.82rem', color: '#a7f3d0', padding: '0.5rem 0.8rem', borderRadius: '8px' }}>
                  <Terminal size={15} />
                  <span>{step.verification_command}</span>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
