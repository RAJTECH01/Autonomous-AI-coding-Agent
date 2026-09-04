import React, { useState } from 'react';
import axios from 'axios';
import { Play, Terminal, Cpu, AlertCircle, RefreshCw } from 'lucide-react';

interface SessionState {
  session_id: string;
  status: string;
  user_prompt: string;
  ai_provider: string;
  model_name: string;
  current_iteration: number;
  execution_summary: Record<string, any>;
}

export const SessionWorkspace: React.FC = () => {
  const [prompt, setPrompt] = useState('');
  const [provider, setProvider] = useState('anthropic');
  const [model, setModel] = useState('claude-3-5-sonnet-20241022');
  const [loading, setLoading] = useState(false);
  const [activeSession, setActiveSession] = useState<SessionState | null>(null);
  const [error, setError] = useState<string | null>(null);

  const startSession = async () => {
    if (!prompt.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await axios.post('/api/v1/sessions', {
        prompt,
        ai_provider: provider,
        model_name: model,
        max_iterations: 15,
      });
      setActiveSession(res.data);
      pollSession(res.data.session_id);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to initialize agent session');
    } finally {
      setLoading(false);
    }
  };

  const pollSession = (id: string) => {
    const interval = setInterval(async () => {
      try {
        const res = await axios.get(`/api/v1/sessions/${id}`);
        setActiveSession(res.data);
        if (['completed', 'failed', 'cancelled'].includes(res.data.status)) {
          clearInterval(interval);
        }
      } catch {
        // Stop polling on any error rather than hammering a failing endpoint
        // every 2 seconds. The error object is intentionally not inspected.
        clearInterval(interval);
      }
    }, 2000);
  };

  return (
    <div className="workspace-grid">
      <div className="sidebar">
        <h2>Agent Configuration</h2>
        
        <div>
          <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.85rem' }}>AI Model Provider</label>
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            <option value="anthropic">Anthropic (Claude 3.5)</option>
            <option value="openai">OpenAI (GPT-4o)</option>
            <option value="gemini">Google Gemini</option>
          </select>
        </div>

        <div>
          <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.85rem' }}>Model Name</label>
          <input type="text" value={model} onChange={(e) => setModel(e.target.value)} />
        </div>

        <div>
          <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.85rem' }}>Requirement Prompt</label>
          <textarea
            rows={6}
            placeholder="e.g. Add JWT authentication middleware to FastAPI backend and write unit tests using pytest..."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
        </div>

        <button className="btn" onClick={startSession} disabled={loading || !prompt.trim()}>
          {loading ? <RefreshCw className="spin" size={18} /> : <Play size={18} />}
          <span>{loading ? 'Initializing Agent...' : 'Launch Agent Loop'}</span>
        </button>

        {error && (
          <div style={{ color: '#ef4444', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}
      </div>

      <div className="main-content">
        {!activeSession ? (
          <div className="card" style={{ textAlign: 'center', padding: '4rem 2rem' }}>
            <Cpu size={48} color="var(--accent-cyan)" style={{ marginBottom: '1rem' }} />
            <h3>No Active Agent Session</h3>
            <p style={{ color: 'var(--text-muted)', marginTop: '0.5rem' }}>
              Configure your requirements on the left sidebar to start the autonomous development loop.
            </p>
          </div>
        ) : (
          <>
            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <span className={`status-badge status-${activeSession.status}`}>
                    {activeSession.status}
                  </span>
                  <h3 style={{ marginTop: '0.5rem' }}>{activeSession.user_prompt}</h3>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Iteration</div>
                  <div style={{ fontSize: '1.5rem', fontWeight: '700', color: 'var(--accent-cyan)' }}>
                    {activeSession.current_iteration} / 15
                  </div>
                </div>
              </div>
            </div>

            <div className="card">
              <h4 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
                <Terminal size={20} color="var(--accent-emerald)" />
                <span>Execution Output Stream</span>
              </h4>
              <div className="log-stream">
                {JSON.stringify(activeSession.execution_summary, null, 2)}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
