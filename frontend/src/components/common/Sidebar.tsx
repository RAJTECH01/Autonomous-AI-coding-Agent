import React from 'react';
import {
  LayoutDashboard,
  Folder,
  PlusCircle,
  PlayCircle,
  FileCode2,
  History,
  Terminal,
  Settings,
  Layers,
} from 'lucide-react';
import { useNavigationStore, PageName } from '../../store/useNavigationStore';
import { useAgentExecutionStore } from '../../store/useAgentExecutionStore';

interface NavItem {
  page: PageName;
  label: string;
  icon: React.ReactNode;
  badge?: string;
}

export const Sidebar: React.FC = () => {
  const { currentPage, navigate } = useNavigationStore();
  const { activeExecution } = useAgentExecutionStore();

  const navItems: NavItem[] = [
    { page: 'dashboard', label: 'Dashboard', icon: <LayoutDashboard size={18} /> },
    { page: 'projects', label: 'Projects', icon: <Folder size={18} /> },
    { page: 'new_task', label: 'New Coding Task', icon: <PlusCircle size={18} /> },
    {
      page: 'agent_execution',
      label: 'Agent Execution',
      icon: <PlayCircle size={18} />,
      badge: activeExecution ? activeExecution.status : undefined,
    },
    { page: 'files', label: 'Project Files', icon: <FileCode2 size={18} /> },
    { page: 'task_history', label: 'Task History', icon: <History size={18} /> },
    { page: 'agent_logs', label: 'Agent Logs', icon: <Terminal size={18} /> },
    { page: 'settings', label: 'Settings', icon: <Settings size={18} /> },
  ];

  return (
    <aside
      style={{
        width: '250px',
        padding: '1.25rem 0.85rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.6rem',
        height: '100%',
        flexShrink: 0,
      }}
    >
      <div style={{ padding: '0.2rem 0.6rem 0.75rem', fontSize: '0.72rem', fontWeight: 800, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        Navigation
      </div>
      {navItems.map((item) => {
        const isActive = currentPage === item.page || (item.page === 'projects' && currentPage === 'project_details');
        return (
          <button
            key={item.page}
            onClick={() => navigate(item.page)}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              width: '100%',
              padding: '0.72rem 0.95rem',
              borderRadius: '12px',
              border: isActive ? '1px solid rgba(192, 132, 252, 0.5)' : '1px solid transparent',
              background: isActive
                ? 'linear-gradient(135deg, rgba(168, 85, 247, 0.25) 0%, rgba(126, 34, 206, 0.3) 100%)'
                : 'transparent',
              color: isActive ? '#ffffff' : 'var(--text-muted)',
              fontWeight: isActive ? 800 : 500,
              fontSize: '0.9rem',
              cursor: 'pointer',
              boxShadow: isActive ? '0 8px 20px -4px rgba(168, 85, 247, 0.35), inset 0 1px 1px rgba(255, 255, 255, 0.4)' : 'none',
              transition: 'all 0.2s ease',
              textAlign: 'left',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <span style={{ color: isActive ? '#ffffff' : 'var(--text-dim)', filter: isActive ? 'drop-shadow(0 0 6px rgba(192, 132, 252, 0.8))' : 'none' }}>
                {item.icon}
              </span>
              <span>{item.label}</span>
            </div>
            {item.badge && (
              <span
                style={{
                  fontSize: '0.66rem',
                  padding: '0.15rem 0.55rem',
                  borderRadius: '12px',
                  background: 'linear-gradient(135deg, rgba(168, 85, 247, 0.35) 0%, rgba(126, 34, 206, 0.35) 100%)',
                  color: '#ffffff',
                  border: '1px solid rgba(192, 132, 252, 0.5)',
                  fontWeight: 800,
                  boxShadow: '0 2px 6px rgba(0,0,0,0.4), inset 0 1px 1px rgba(255,255,255,0.4)',
                }}
              >
                {item.badge}
              </span>
            )}
          </button>
        );
      })}

      <div style={{
        marginTop: 'auto',
        padding: '1rem 0.85rem 0.85rem',
        borderRadius: '12px',
        background: 'rgba(5, 9, 18, 0.6)',
        border: '1px solid var(--glass-border)',
        boxShadow: 'var(--skeuo-shadow-inset)',
        fontSize: '0.75rem',
        color: 'var(--text-muted)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--text-main)', fontWeight: 700, marginBottom: '0.25rem' }}>
          <Layers size={14} color="var(--accent-purple)" /> Prompt v1.0.0
        </div>
        <span>A/B Variant Enabled • Pydantic Validated</span>
      </div>
    </aside>
  );
};
