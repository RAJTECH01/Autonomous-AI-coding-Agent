import React, { useState } from 'react';
import { useProjectStore } from '../store/useProjectStore';
import { FileViewer } from '../components/agent/FileViewer';
import { FileCode2 } from 'lucide-react';

export const FilesPage: React.FC = () => {
  const { projects, projectFiles } = useProjectStore();
  const [selectedProjectId, setSelectedProjectId] = useState(projects[0]?.id || '');

  const files = projectFiles[selectedProjectId] || [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <FileCode2 size={26} color="var(--accent-cyan)" style={{ filter: 'drop-shadow(0 0 6px var(--accent-cyan-glow))' }} /> Workspace Source Files Explorer
          </h2>
          <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            Inspect source files monitored by the autonomous agent loop.
          </p>
        </div>

        <div style={{ width: '280px' }}>
          <select value={selectedProjectId} onChange={(e) => setSelectedProjectId(e.target.value)}>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <FileViewer files={files} />
    </div>
  );
};
