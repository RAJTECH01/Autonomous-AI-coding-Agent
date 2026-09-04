import React from 'react';
import { Cpu, ShieldCheck, User as UserIcon, LogOut } from 'lucide-react';
import { useAuthStore } from '../../store/useAuthStore';
import { useNavigationStore } from '../../store/useNavigationStore';

export const Header: React.FC = () => {
  const { user, isAuthenticated, logout } = useAuthStore();
  const { navigate } = useNavigationStore();

  return (
    <header>
      <div className="brand" onClick={() => navigate('dashboard')} style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <div style={{
          background: 'linear-gradient(135deg, rgba(168,85,247,0.4) 0%, rgba(126,34,206,0.4) 100%)',
          padding: '0.5rem',
          borderRadius: '12px',
          border: '1px solid rgba(255,255,255,0.3)',
          boxShadow: 'var(--skeuo-shadow-raised)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}>
          <Cpu size={22} color="#ffffff" style={{ filter: 'drop-shadow(0 0 6px rgba(168,85,247,0.8))' }} />
        </div>
        <span style={{
          fontSize: '1.18rem',
          fontWeight: 800,
          letterSpacing: '0.8px',
          background: 'linear-gradient(135deg, #ffffff 0%, #c084fc 50%, #a855f7 100%)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.7))'
        }}>
          AUTONOMOUS AGENT PLATFORM
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem' }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          color: '#ffffff',
          fontSize: '0.82rem',
          fontWeight: 700,
          background: 'linear-gradient(135deg, rgba(168, 85, 247, 0.25) 0%, rgba(126, 34, 206, 0.2) 100%)',
          padding: '0.4rem 0.85rem',
          borderRadius: '20px',
          border: '1px solid rgba(192, 132, 252, 0.4)',
          boxShadow: '0 4px 12px rgba(168, 85, 247, 0.25), inset 0 1px 1px rgba(255,255,255,0.4)'
        }}>
          <span className="pulse-dot pulse-dot-emerald"></span>
          <ShieldCheck size={15} color="#c084fc" /> Sandbox Isolated (Docker / gVisor)
        </div>

        {isAuthenticated && user ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
            <div
              onClick={() => navigate('settings')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.6rem',
                cursor: 'pointer',
                padding: '0.4rem 0.85rem',
                borderRadius: '12px',
                background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.8) 100%)',
                border: '1px solid var(--glass-border)',
                boxShadow: 'var(--skeuo-shadow-raised)',
                transition: 'all 0.2s ease'
              }}
            >
              <UserIcon size={16} color="var(--accent-cyan)" />
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-main)' }}>{user.full_name}</span>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', background: 'rgba(255,255,255,0.1)', padding: '0.1rem 0.4rem', borderRadius: '6px' }}>{user.role}</span>
            </div>
            <button
              onClick={() => {
                logout();
                navigate('login');
              }}
              title="Sign Out"
              className="btn btn-secondary"
              style={{ padding: '0.45rem 0.65rem', borderRadius: '10px' }}
            >
              <LogOut size={16} />
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', gap: '0.6rem' }}>
            <button className="btn" style={{ padding: '0.45rem 1.1rem', fontSize: '0.85rem' }} onClick={() => navigate('login')}>Login</button>
            <button className="btn btn-secondary" style={{ padding: '0.45rem 1.1rem', fontSize: '0.85rem' }} onClick={() => navigate('register')}>Register</button>
          </div>
        )}
      </div>
    </header>
  );
};
