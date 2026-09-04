import React, { useState } from 'react';
import { useProjectStore } from '../store/useProjectStore';
import { useNavigationStore } from '../store/useNavigationStore';
import { Folder, Plus, Search, FileCode2, History, ArrowRight } from 'lucide-react';

export const ProjectsPage: React.FC = () => {
  const { projects, addProject } = useProjectStore();
  const { navigate } = useNavigationStore();
  const [searchTerm, setSearchTerm] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);

  // New Project Form
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [language, setLanguage] = useState('Python');
  const [framework, setFramework] = useState('FastAPI');

  const filteredProjects = projects.filter(
    (p) =>
      p.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.description.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleCreateProject = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name) return;

    const newProj = {
      id: `proj-${Date.now()}`,
      name,
      slug: name.toLowerCase().replace(/\s+/g, '-'),
      description,
      language,
      framework,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      files_count: 5,
      tasks_count: 0,
    };

    addProject(newProj);
    setIsModalOpen(false);
    setName('');
    setDescription('');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
      {/* Top Action Bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <Folder size={26} color="var(--accent-cyan)" style={{ filter: 'drop-shadow(0 0 6px var(--accent-cyan-glow))' }} /> Managed Workspaces & Projects
          </h2>
          <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            Browse codebases registered for autonomous coding agent tasks.
          </p>
        </div>

        <button
          className="btn"
          onClick={() => setIsModalOpen(true)}
        >
          <Plus size={18} /> Register New Project
        </button>
      </div>

      {/* Search Input */}
      <div style={{ position: 'relative', maxWidth: '440px' }}>
        <input
          type="text"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder="Search projects by name or description..."
          style={{ paddingLeft: '2.75rem' }}
        />
        <Search size={18} color="var(--text-dim)" style={{ position: 'absolute', left: '0.95rem', top: '50%', transform: 'translateY(-50%)' }} />
      </div>

      {/* Project Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1.35rem' }}>
        {filteredProjects.map((proj) => (
          <div
            key={proj.id}
            className="glass-panel glass-panel-interactive"
            style={{
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              gap: '1.1rem',
              padding: '1.35rem',
            }}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.65rem' }}>
                <span style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--text-main)' }}>
                  {proj.name}
                </span>
                <span
                  style={{
                    fontSize: '0.7rem',
                    padding: '0.15rem 0.55rem',
                    borderRadius: '10px',
                    background: 'linear-gradient(135deg, rgba(0, 242, 254, 0.25) 0%, rgba(59, 130, 246, 0.25) 100%)',
                    color: 'var(--accent-cyan)',
                    border: '1px solid rgba(0, 242, 254, 0.4)',
                    fontWeight: 700,
                    boxShadow: '0 2px 6px rgba(0,0,0,0.3)',
                  }}
                >
                  {proj.language}
                </span>
              </div>

              <p style={{ fontSize: '0.88rem', color: 'var(--text-muted)', lineHeight: '1.45', marginBottom: '1.1rem' }}>
                {proj.description}
              </p>

              <div style={{ display: 'flex', alignItems: 'center', gap: '1.35rem', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                  <FileCode2 size={15} color="var(--accent-purple)" /> {proj.files_count} files
                </span>
                <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                  <History size={15} color="#34d399" /> {proj.tasks_count} tasks
                </span>
              </div>
            </div>

            <div style={{ display: 'flex', gap: '0.6rem', paddingTop: '0.85rem', borderTop: '1px solid var(--glass-border)' }}>
              <button
                className="btn"
                onClick={() => navigate('project_details', { projectId: proj.id })}
                style={{ flex: 1, padding: '0.55rem', fontSize: '0.85rem' }}
              >
                View Details <ArrowRight size={14} />
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => navigate('new_task', { projectId: proj.id })}
                style={{ padding: '0.55rem 0.95rem', fontSize: '0.85rem' }}
              >
                + Task
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Register Project Modal */}
      {isModalOpen && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(3, 7, 18, 0.8)', backdropFilter: 'blur(16px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div className="glass-panel" style={{ width: '100%', maxWidth: '500px', padding: '2.25rem', border: '1px solid rgba(255, 255, 255, 0.25)', boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.8)' }}>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 800, marginBottom: '1.35rem', color: 'var(--text-main)' }}>
              Register New Project Workspace
            </h3>

            <form onSubmit={handleCreateProject} style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem' }}>
              <div>
                <label style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted)', display: 'block', marginBottom: '0.45rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Project Name
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Payment Gateway Service"
                  required
                />
              </div>

              <div>
                <label style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted)', display: 'block', marginBottom: '0.45rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Description
                </label>
                <textarea
                  rows={3}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Brief summary of codebase domain..."
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.1rem' }}>
                <div>
                  <label style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted)', display: 'block', marginBottom: '0.45rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Primary Language
                  </label>
                  <select value={language} onChange={(e) => setLanguage(e.target.value)}>
                    <option value="Python">Python</option>
                    <option value="TypeScript">TypeScript</option>
                    <option value="Go">Go</option>
                    <option value="Rust">Rust</option>
                    <option value="Java">Java</option>
                  </select>
                </div>

                <div>
                  <label style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted)', display: 'block', marginBottom: '0.45rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Framework
                  </label>
                  <input
                    type="text"
                    value={framework}
                    onChange={(e) => setFramework(e.target.value)}
                    placeholder="e.g. FastAPI / React"
                  />
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.85rem', marginTop: '1.25rem' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setIsModalOpen(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn">
                  Create Project
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
