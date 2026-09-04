import React, { useState } from 'react';
import { useAuthStore } from '../store/useAuthStore';
import { useNavigationStore } from '../store/useNavigationStore';
import { Cpu, Lock, Mail, ArrowRight } from 'lucide-react';

export const LoginPage: React.FC = () => {
  const [email, setEmail] = useState('dev@example.com');
  const [password, setPassword] = useState('password123');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const { login } = useAuthStore();
  const { navigate } = useNavigationStore();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setError('Please enter both email and password.');
      return;
    }
    setIsLoading(true);
    setTimeout(() => {
      login(email, 'jwt-token-demo-990', {
        id: 'u-101',
        email,
        full_name: 'Lead Autonomous Engineer',
        role: 'developer',
        created_at: new Date().toISOString(),
      });
      setIsLoading(false);
      navigate('dashboard');
    }, 600);
  };

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: 'calc(100vh - 75px)',
        padding: '2rem',
      }}
    >
      <div
        className="glass-panel"
        style={{
          width: '100%',
          maxWidth: '440px',
          padding: '2.75rem 2.25rem',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.75), inset 0 1px 1px rgba(255,255,255,0.3)',
          border: '1px solid rgba(255, 255, 255, 0.2)',
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: '2.25rem' }}>
          <div
            style={{
              width: '60px',
              height: '60px',
              borderRadius: '18px',
              background: 'linear-gradient(135deg, rgba(0, 242, 254, 0.3) 0%, rgba(157, 78, 221, 0.3) 100%)',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: '1.25rem',
              border: '1px solid rgba(255, 255, 255, 0.3)',
              boxShadow: 'var(--skeuo-shadow-raised)',
            }}
          >
            <Cpu size={30} color="var(--accent-cyan)" style={{ filter: 'drop-shadow(0 0 8px var(--accent-cyan-glow))' }} />
          </div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 800, color: '#fff', letterSpacing: '-0.01em' }}>
            Welcome Back
          </h2>
          <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginTop: '0.35rem' }}>
            Sign in to your Autonomous Agent Command Center
          </p>
        </div>

        {error && (
          <div
            style={{
              background: 'linear-gradient(135deg, rgba(244, 63, 94, 0.2) 0%, rgba(185, 28, 28, 0.15) 100%)',
              border: '1px solid rgba(251, 113, 133, 0.35)',
              color: '#fca5a5',
              padding: '0.85rem',
              borderRadius: '12px',
              fontSize: '0.86rem',
              marginBottom: '1.5rem',
              boxShadow: '0 4px 12px rgba(244,63,94,0.2)',
            }}
          >
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.35rem' }}>
          <div>
            <label style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted)', display: 'block', marginBottom: '0.45rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Email Address
            </label>
            <div style={{ position: 'relative' }}>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="dev@company.com"
                style={{ paddingLeft: '2.75rem' }}
              />
              <Mail size={18} color="var(--text-dim)" style={{ position: 'absolute', left: '0.95rem', top: '50%', transform: 'translateY(-50%)' }} />
            </div>
          </div>

          <div>
            <label style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted)', display: 'block', marginBottom: '0.45rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Password
            </label>
            <div style={{ position: 'relative' }}>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                style={{ paddingLeft: '2.75rem' }}
              />
              <Lock size={18} color="var(--text-dim)" style={{ position: 'absolute', left: '0.95rem', top: '50%', transform: 'translateY(-50%)' }} />
            </div>
          </div>

          <button
            type="submit"
            className="btn"
            disabled={isLoading}
            style={{ width: '100%', padding: '0.85rem', marginTop: '0.6rem' }}
          >
            {isLoading ? 'Signing In...' : 'Sign In to Console'}
            {!isLoading && <ArrowRight size={18} />}
          </button>
        </form>

        <div style={{ marginTop: '2rem', textAlign: 'center', fontSize: '0.88rem', color: 'var(--text-muted)' }}>
          Don't have an account?{' '}
          <span onClick={() => navigate('register')} style={{ color: 'var(--accent-cyan)', cursor: 'pointer', fontWeight: 700 }}>
            Create one here
          </span>
        </div>
      </div>
    </div>
  );
};
