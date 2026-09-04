import React, { useState } from 'react';
import { Settings, ShieldCheck, Sliders, Cpu, Save } from 'lucide-react';

export const SettingsPage: React.FC = () => {
  const [provider, setProvider] = useState('anthropic');
  const [model, setModel] = useState('claude-3-5-sonnet-20241022');
  const [sandboxEngine, setSandboxEngine] = useState('docker-gvisor');
  const [maxIterationsDefault, setMaxIterationsDefault] = useState(20);
  const [requireHumanApprovalDefault, setRequireHumanApprovalDefault] = useState(true);
  const [savedSuccess, setSavedSuccess] = useState(false);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 3000);
  };

  return (
    <div style={{ maxWidth: '800px', display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
      <div>
        <h2 style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <Settings size={26} color="var(--accent-cyan)" style={{ filter: 'drop-shadow(0 0 6px var(--accent-cyan-glow))' }} /> Platform Settings & Preferences
        </h2>
        <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
          Configure default agent execution limits, provider routing, and sandbox environment isolation.
        </p>
      </div>

      {savedSuccess && (
        <div
          style={{
            background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.25) 0%, rgba(5, 150, 105, 0.2) 100%)',
            border: '1px solid rgba(52, 211, 153, 0.4)',
            color: '#34d399',
            padding: '0.95rem 1.25rem',
            borderRadius: '12px',
            fontSize: '0.9rem',
            fontWeight: 700,
            boxShadow: '0 4px 12px rgba(16,185,129,0.2)',
          }}
        >
          Settings updated successfully!
        </div>
      )}

      <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        {/* Section 1: AI Provider */}
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 800, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <Cpu size={20} color="var(--accent-cyan)" style={{ filter: 'drop-shadow(0 0 6px var(--accent-cyan-glow))' }} /> AI Model Provider Defaults
          </h3>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem' }}>
            <div>
              <label style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted)', display: 'block', marginBottom: '0.45rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Primary LLM Provider
              </label>
              <select value={provider} onChange={(e) => setProvider(e.target.value)}>
                <option value="anthropic">Anthropic (Claude 3.5 Sonnet)</option>
                <option value="openai">OpenAI (GPT-4o / GPT-4 Turbo)</option>
                <option value="gemini">Google Gemini (Gemini 1.5 Pro)</option>
              </select>
            </div>

            <div>
              <label style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted)', display: 'block', marginBottom: '0.45rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Model Identifier
              </label>
              <input
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="claude-3-5-sonnet-20241022"
              />
            </div>
          </div>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>
            Note: Provider API keys are managed securely on the backend server environment and are never exposed to client browsers.
          </span>
        </div>

        {/* Section 2: Sandbox Security */}
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 800, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <ShieldCheck size={20} color="#34d399" style={{ filter: 'drop-shadow(0 0 6px rgba(52,211,153,0.5))' }} /> Code Sandbox Isolation Engine
          </h3>

          <div>
            <label style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted)', display: 'block', marginBottom: '0.45rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Sandbox Security Adapter
            </label>
            <select value={sandboxEngine} onChange={(e) => setSandboxEngine(e.target.value)}>
              <option value="docker-gvisor">Docker + gVisor MicroVM Container Isolation (Recommended)</option>
              <option value="docker-standard">Standard Unprivileged Docker Container</option>
              <option value="local-chroot">Local Chroot Process Isolation (Dev Only)</option>
            </select>
          </div>
        </div>

        {/* Section 3: Agent Execution Defaults */}
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 800, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <Sliders size={20} color="var(--accent-purple)" style={{ filter: 'drop-shadow(0 0 6px var(--accent-purple-glow))' }} /> Task Defaults & Approval Settings
          </h3>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem' }}>
            <div>
              <label style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted)', display: 'block', marginBottom: '0.45rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Default Max Iterations Limit
              </label>
              <input
                type="number"
                value={maxIterationsDefault}
                onChange={(e) => setMaxIterationsDefault(parseInt(e.target.value) || 1)}
                min={1}
                max={50}
              />
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem', paddingTop: '1.5rem' }}>
              <input
                type="checkbox"
                checked={requireHumanApprovalDefault}
                onChange={(e) => setRequireHumanApprovalDefault(e.target.checked)}
                style={{ width: '20px', height: '20px', cursor: 'pointer', accentColor: 'var(--accent-cyan)' }}
              />
              <span style={{ fontSize: '0.88rem', color: 'var(--text-main)', fontWeight: 600 }}>
                Default to requiring human approval before implementation
              </span>
            </div>
          </div>
        </div>

        <button type="submit" className="btn" style={{ width: 'fit-content', padding: '0.9rem 2rem' }}>
          <Save size={20} /> Save Settings Preferences
        </button>
      </form>
    </div>
  );
};
