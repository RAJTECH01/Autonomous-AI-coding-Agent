import { create } from 'zustand';
import { Project, ProjectFile } from '../types/project';

interface ProjectStoreState {
  projects: Project[];
  activeProject: Project | null;
  projectFiles: Record<string, ProjectFile[]>; // projectId -> files
  isLoading: boolean;
  error: string | null;
  setProjects: (projects: Project[]) => void;
  setActiveProject: (project: Project | null) => void;
  addProject: (project: Project) => void;
}

const DEFAULT_PROJECTS: Project[] = [
  {
    id: 'proj-auth-service',
    name: 'Authentication Microservice',
    slug: 'auth-service',
    description: 'FastAPI microservice handling JWT authentication, OAuth2, and Argon2 password hashing.',
    language: 'Python',
    framework: 'FastAPI + SQLAlchemy',
    created_at: new Date(Date.now() - 7 * 86400000).toISOString(),
    updated_at: new Date().toISOString(),
    files_count: 14,
    tasks_count: 5,
  },
  {
    id: 'proj-agent-core',
    name: 'Autonomous Agent Engine',
    slug: 'agent-core',
    description: 'State machine architecture executing code implementation, sandbox command isolation, and code reviews.',
    language: 'Python',
    framework: 'FastAPI + Docker',
    created_at: new Date(Date.now() - 14 * 86400000).toISOString(),
    updated_at: new Date().toISOString(),
    files_count: 28,
    tasks_count: 12,
  },
  {
    id: 'proj-react-frontend',
    name: 'Web Management Console',
    slug: 'react-frontend',
    description: 'React + TypeScript dashboard rendering live agent execution states, tool calls, and review findings.',
    language: 'TypeScript',
    framework: 'React + Vite',
    created_at: new Date(Date.now() - 3 * 86400000).toISOString(),
    updated_at: new Date().toISOString(),
    files_count: 22,
    tasks_count: 4,
  },
];

const DEFAULT_FILES: Record<string, ProjectFile[]> = {
  'proj-auth-service': [
    { id: 'f1', file_path: 'backend/app/main.py', size_bytes: 1420, last_modified: new Date().toISOString() },
    { id: 'f2', file_path: 'backend/app/core/security.py', size_bytes: 2850, last_modified: new Date().toISOString() },
    { id: 'f3', file_path: 'backend/app/api/v1/endpoints/auth.py', size_bytes: 4120, last_modified: new Date().toISOString() },
    { id: 'f4', file_path: 'backend/app/domain/entities/user.py', size_bytes: 980, last_modified: new Date().toISOString() },
    { id: 'f5', file_path: 'backend/tests/test_auth.py', size_bytes: 3100, last_modified: new Date().toISOString() },
  ],
  'proj-agent-core': [
    { id: 'f6', file_path: 'backend/app/application/agent/state_machine.py', size_bytes: 20420, last_modified: new Date().toISOString() },
    { id: 'f7', file_path: 'backend/app/application/agent/subagents/reviewer.py', size_bytes: 9694, last_modified: new Date().toISOString() },
    { id: 'f8', file_path: 'backend/app/application/agent/subagents/debugger.py', size_bytes: 11050, last_modified: new Date().toISOString() },
    { id: 'f9', file_path: 'backend/app/core/prompts/manager.py', size_bytes: 10783, last_modified: new Date().toISOString() },
  ],
  'proj-react-frontend': [
    { id: 'f10', file_path: 'frontend/src/App.tsx', size_bytes: 875, last_modified: new Date().toISOString() },
    { id: 'f11', file_path: 'frontend/src/pages/AgentExecutionPage.tsx', size_bytes: 5200, last_modified: new Date().toISOString() },
    { id: 'f12', file_path: 'frontend/src/types/agent.ts', size_bytes: 2400, last_modified: new Date().toISOString() },
  ]
};

export const useProjectStore = create<ProjectStoreState>((set) => ({
  projects: DEFAULT_PROJECTS,
  activeProject: DEFAULT_PROJECTS[0],
  projectFiles: DEFAULT_FILES,
  isLoading: false,
  error: null,

  setProjects: (projects) => set({ projects }),
  setActiveProject: (activeProject) => set({ activeProject }),
  addProject: (project) => set((state) => ({ projects: [project, ...state.projects] })),
}));
