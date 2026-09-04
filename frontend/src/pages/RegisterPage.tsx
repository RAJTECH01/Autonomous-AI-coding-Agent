import React, { useState } from 'react';
import { useAuthStore } from '../store/useAuthStore';
import { useNavigationStore } from '../store/useNavigationStore';
import { Cpu, Lock, Mail, User, ArrowRight } from 'lucide-react';

export const RegisterPage: React.FC = () => {
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<'developer' | 'admin'>('developer');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const { login } = useAuthStore();
  const { navigate } = useNavigationStore();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!fullName || !email || !password) {
      setError('Please fill in all required fields.');
      return;
    }
    setIsLoading(true);
    setTimeout(() => {
      login(email, 'jwt-token-new-user', {
        id: `u-${Date.now()}`,
        email,
        full_name: fullName,
        role,
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
          maxWidth: '460px',
          padding: '2.75rem 2.25rem',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.75), inset 0 1px 1px rgba(255,255,255,0.3)',
          border: '1px solid rgba(255, 255, 255, 0.2)',
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
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
            Create Account
          </h2>
          <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginTop: '0.35rem' }}>
            Register to launch autonomous coding agent tasks
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

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem' }}>
          <div>
            <label style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted)', display: 'block', marginBottom: '0.45rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Full Name
            </label>
            <div style={{ position: 'relative' }}>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Jane Doe"
                style={{ paddingLeft: '2.75rem' }}
              />
              <User size={18} color="var(--text-dim)" style={{ position: 'absolute', left: '0.95rem', top: '50%', transform: 'translateY(-50%)' }} />
            </div>
          </div>

          <div>
            <label style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted)', display: 'block', marginBottom: '0.45rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Email Address
            </label>
            <div style={{ position: 'relative' }}>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="jane@company.com"
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

          <div>
            <label style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted)', display: 'block', marginBottom: '0.45rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Role / Access Level
            </label>
            <select value={role} onChange={(e) => setRole(e.target.value as any)}>
              <option value="developer">Developer (Task Creation & Review)</option>
              <option value="admin">System Administrator (Full Access)</option>
            </select>
          </div>

          <button
            type="submit"
            className="btn"
            disabled={isLoading}
            style={{ width: '100%', padding: '0.85rem', marginTop: '0.6rem' }}
          >
            {isLoading ? 'Creating Account...' : 'Complete Registration'}
            {!isLoading && <ArrowRight size={18} />}
          </button>
        </form>

        <div style={{ marginTop: '2rem', textAlign: 'center', fontSize: '0.88rem', color: 'var(--text-muted)' }}>
          Already registered?{' '}
          <span onClick={() => navigate('login')} style={{ color: 'var(--accent-cyan)', cursor: 'pointer', fontWeight: 700 }}>
            Sign in here
          </span>
        </div>
      </div>
    </div>
  );
};
