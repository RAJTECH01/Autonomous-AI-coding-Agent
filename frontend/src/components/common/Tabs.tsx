import React from 'react';

export interface TabItem {
  id: string;
  label: string;
  badge?: string | number;
}

interface TabsProps {
  tabs: TabItem[];
  activeTab: string;
  onChange: (id: string) => void;
}

export const Tabs: React.FC<TabsProps> = ({ tabs, activeTab, onChange }) => {
  return (
    <div className="glass-tabs">
      {tabs.map((tab) => {
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            className={`glass-tab-item ${isActive ? 'active' : ''}`}
            style={{
              whiteSpace: 'nowrap',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
            }}
          >
            <span>{tab.label}</span>
            {tab.badge !== undefined && tab.badge !== null && (
              <span
                style={{
                  fontSize: '0.68rem',
                  padding: '0.15rem 0.5rem',
                  borderRadius: '10px',
                  fontWeight: 700,
                  boxShadow: '0 2px 6px rgba(0,0,0,0.3), inset 0 1px 1px rgba(255,255,255,0.3)',
                  background:
                    tab.badge === 'PASSED'
                      ? 'linear-gradient(135deg, rgba(16, 185, 129, 0.3) 0%, rgba(5, 150, 105, 0.3) 100%)'
                      : tab.badge === 'FAILED' || tab.badge === 'ERROR'
                      ? 'linear-gradient(135deg, rgba(244, 63, 94, 0.3) 0%, rgba(225, 29, 72, 0.3) 100%)'
                      : 'rgba(255, 255, 255, 0.12)',
                  color:
                    tab.badge === 'PASSED'
                      ? '#34d399'
                      : tab.badge === 'FAILED' || tab.badge === 'ERROR'
                      ? '#fb7185'
                      : 'var(--text-main)',
                  border:
                    tab.badge === 'PASSED'
                      ? '1px solid rgba(52,211,153,0.4)'
                      : tab.badge === 'FAILED' || tab.badge === 'ERROR'
                      ? '1px solid rgba(251,113,133,0.4)'
                      : '1px solid rgba(255,255,255,0.15)'
                }}
              >
                {tab.badge}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
};
