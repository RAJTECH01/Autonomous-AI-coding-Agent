import React from 'react';
import { useProjectStore } from '../store/useProjectStore';
import { useAgentExecutionStore } from '../store/useAgentExecutionStore';
import { useNavigationStore } from '../store/useNavigationStore';
import { AgentStateBadge } from '../components/agent/AgentStateBadge';
import { Folder, FileCode2, History, PlusCircle, ArrowLeft, Code } from 'lucide-react';

export const ProjectDetailsPage: React.FC = () => {
  const { projects, projectFiles } = useProjectStore();
  const { tasks } = useAgentExecutionStore();
  const { params, navigate } = useNavigationStore();

  const project = projects.find((p) => p.id === params.projectId) || projects[0];
  const files = projectFiles[project?.id || ''] || [];
  const projectTasks = tasks.filter((t) => t.project_id === project?.id);

  if (!project) {
    return <div className="glass-panel" style={{ padding: '2rem', textAlign: 'center' }}>Project not found.</div>;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
      {/* Header Bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <button
            onClick={() => navigate('projects')}
            className="btn btn-secondary"
            style={{ padding: '0.45rem 0.85rem', fontSize: '0.85rem' }}
          >
            <ArrowLeft size={16} /> Back
          </button>
          <div>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <Folder size={26} color="var(--accent-cyan)" style={{ filter: 'drop-shadow(0 0 6px var(--accent-cyan-glow))' }} /> {project.name}
            </h2>
            <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
              {project.description}
            </p>
          </div>
        </div>

        <button
          className="btn"
          onClick={() => navigate('new_task', { projectId: project.id })}
        >
          <PlusCircle size={18} /> Launch Task on Project
        </button>
      </div>

      {/* Stats Summary */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.25rem' }}>
        <div className="glass-panel glass-panel-interactive" style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', padding: '1.25rem' }}>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 800, letterSpacing: '0.05em' }}>Language & Framework</span>
          <span style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--accent-cyan)', textShadow: '0 0 8px var(--accent-cyan-glow)' }}>{project.language} • {project.framework}</span>
        </div>

        <div className="glass-panel glass-panel-interactive" style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', padding: '1.25rem' }}>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 800, letterSpacing: '0.05em' }}>Monitored Source Files</span>
          <span style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--accent-purple)', textShadow: '0 0 8px var(--accent-purple-glow)' }}>{files.length} Files</span>
        </div>

        <div className="glass-panel glass-panel-interactive" style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', padding: '1.25rem' }}>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 800, letterSpacing: '0.05em' }}>Executed Coding Tasks</span>
          <span style={{ fontSize: '1.25rem', fontWeight: 800, color: '#34d399', textShadow: '0 0 8px rgba(52,211,153,0.4)' }}>{projectTasks.length} Tasks</span>
        </div>
      </div>

      {/* Main Grid: Files & Task History */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
        {/* Source Files */}
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 800, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '0.55rem' }}>
              <FileCode2 size={18} color="var(--accent-cyan)" style={{ filter: 'drop-shadow(0 0 6px var(--accent-cyan-glow))' }} /> Monitored Files ({files.length})
            </h3>
            <button
              onClick={() => navigate('files', { projectId: project.id })}
              style={{ background: 'transparent', border: 'none', color: 'var(--accent-cyan)', cursor: 'pointer', fontSize: '0.82rem', fontWeight: 700 }}
            >
              Open File Explorer
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            {files.map((file) => (
              <div
                key={file.id}
                style={{
                  padding: '0.7rem 0.95rem',
                  borderRadius: '10px',
                  background: 'rgba(5, 9, 18, 0.75)',
                  border: '1px solid var(--glass-border)',
                  boxShadow: 'var(--skeuo-shadow-inset)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  fontSize: '0.86rem',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.55rem' }}>
                  <Code size={15} color="var(--accent-purple)" />
                  <span style={{ color: 'var(--text-main)', fontWeight: 600 }}>{file.file_path}</span>
                </div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', background: 'rgba(255,255,255,0.06)', padding: '0.15rem 0.5rem', borderRadius: '6px' }}>{file.size_bytes} B</span>
              </div>
            ))}
          </div>
        </div>

        {/* Project Tasks */}
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.1rem' }}>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 800, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '0.55rem' }}>
            <History size={18} color="#34d399" style={{ filter: 'drop-shadow(0 0 6px rgba(52,211,153,0.5))' }} /> Tasks History ({projectTasks.length})
          </h3>

          {projectTasks.length === 0 ? (
            <div style={{ padding: '2.5rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.92rem' }}>
              No tasks launched on this project yet.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
              {projectTasks.map((t) => (
                <div
                  key={t.id}
                  onClick={() => {
                    if (t.last_run_id) {
                      useAgentExecutionStore.getState().setActiveExecutionByRunId(t.last_run_id);
                    }
                    navigate('agent_execution', { taskId: t.id, runId: t.last_run_id });
                  }}
                  style={{
                    padding: '0.95rem 1.1rem',
                    borderRadius: '12px',
                    background: 'rgba(5, 9, 18, 0.75)',
                    border: '1px solid var(--glass-border)',
                    boxShadow: 'var(--skeuo-shadow-raised)',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    transition: 'all 0.2s ease',
                  }}
                >
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', maxWidth: '70%' }}>
                    <span style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--text-main)' }}>
                      {t.title}
                    </span>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      Started: {new Date(t.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                  <AgentStateBadge state={t.status} size="sm" />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
