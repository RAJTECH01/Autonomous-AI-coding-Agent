import React, { useState } from 'react';
import { ProjectFile } from '../../types/project';
import { FileCode, Eye } from 'lucide-react';

interface FileViewerProps {
  files: ProjectFile[];
  inspectedFiles?: string[];
  modifiedFiles?: string[];
}

export const FileViewer: React.FC<FileViewerProps> = ({
  files,
  inspectedFiles = [],
  modifiedFiles = [],
}) => {
  const [selectedFile, setSelectedFile] = useState<ProjectFile | null>(files[0] || null);

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '270px 1fr', gap: '1.25rem', height: '560px' }}>
      {/* File List */}
      <div className="glass-panel" style={{ padding: '1rem', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        <h4 style={{ fontSize: '0.78rem', fontWeight: 800, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.4rem' }}>
          Workspace Explorer ({files.length})
        </h4>

        {files.map((file) => {
          const isInspected = inspectedFiles.includes(file.file_path);
          const isModified = modifiedFiles.includes(file.file_path);
          const isSelected = selectedFile?.id === file.id;

          return (
            <div
              key={file.id}
              onClick={() => setSelectedFile(file)}
              style={{
                padding: '0.65rem 0.85rem',
                borderRadius: '10px',
                background: isSelected
                  ? 'linear-gradient(135deg, rgba(0, 242, 254, 0.2) 0%, rgba(59, 130, 246, 0.2) 100%)'
                  : 'rgba(5, 9, 18, 0.6)',
                border: isSelected ? '1px solid rgba(0, 242, 254, 0.5)' : '1px solid var(--glass-border)',
                boxShadow: isSelected ? '0 4px 12px rgba(0, 242, 254, 0.2), inset 0 1px 1px rgba(255,255,255,0.3)' : 'var(--skeuo-shadow-inset)',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                fontSize: '0.82rem',
                fontFamily: 'var(--font-mono)',
                transition: 'all 0.2s ease',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.55rem', overflow: 'hidden' }}>
                <FileCode size={16} color={isModified ? 'var(--accent-emerald)' : 'var(--accent-cyan)'} style={{ filter: 'drop-shadow(0 0 4px rgba(0,242,254,0.4))' }} />
                <span style={{ color: isSelected ? '#fff' : 'var(--text-main)', fontWeight: isSelected ? 700 : 500, textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                  {file.file_path.split('/').pop()}
                </span>
              </div>

              {isModified ? (
                <span style={{ fontSize: '0.66rem', background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.3) 0%, rgba(5, 150, 105, 0.3) 100%)', color: '#34d399', border: '1px solid rgba(52,211,153,0.4)', padding: '0.1rem 0.45rem', borderRadius: '8px', fontWeight: 800 }}>
                  MOD
                </span>
              ) : isInspected ? (
                <span style={{ fontSize: '0.66rem', background: 'linear-gradient(135deg, rgba(0, 242, 254, 0.3) 0%, rgba(59, 130, 246, 0.3) 100%)', color: 'var(--accent-cyan)', border: '1px solid rgba(0,242,254,0.4)', padding: '0.1rem 0.45rem', borderRadius: '8px', fontWeight: 800 }}>
                  READ
                </span>
              ) : null}
            </div>
          );
        })}
      </div>

      {/* File Editor Preview */}
      <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', padding: '1.25rem' }}>
        {selectedFile ? (
          <>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingBottom: '0.85rem', borderBottom: '1px solid var(--glass-border)', marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontFamily: 'var(--font-mono)', fontSize: '0.9rem', fontWeight: 700, color: 'var(--accent-cyan)' }}>
                <Eye size={18} style={{ filter: 'drop-shadow(0 0 6px var(--accent-cyan-glow))' }} />
                <span>{selectedFile.file_path}</span>
              </div>
              <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', background: 'rgba(255,255,255,0.08)', padding: '0.2rem 0.6rem', borderRadius: '8px', border: '1px solid var(--glass-border)' }}>
                {selectedFile.size_bytes} bytes
              </span>
            </div>

            <pre
              className="skeuo-inset"
              style={{
                margin: 0,
                color: '#f3f4f6',
                fontFamily: 'var(--font-mono)',
                fontSize: '0.86rem',
                padding: '1.25rem',
                flex: 1,
                overflowY: 'auto',
                lineHeight: '1.55',
              }}
            >
              {selectedFile.content || `// Content preview for ${selectedFile.file_path}\n// File monitored by autonomous agent loop.`}
            </pre>
          </>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: '0.95rem' }}>
            Select a file from the explorer to preview its contents.
          </div>
        )}
      </div>
    </div>
  );
};
