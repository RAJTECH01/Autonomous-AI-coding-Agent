import { create } from 'zustand';

export type PageName =
  | 'login'
  | 'register'
  | 'dashboard'
  | 'projects'
  | 'project_details'
  | 'new_task'
  | 'agent_execution'
  | 'files'
  | 'task_history'
  | 'agent_logs'
  | 'settings';

interface NavigationState {
  currentPage: PageName;
  params: {
    projectId?: string;
    taskId?: string;
    runId?: string;
    fileId?: string;
  };
  navigate: (page: PageName, params?: NavigationState['params']) => void;
}

export const useNavigationStore = create<NavigationState>((set) => ({
  currentPage: 'dashboard',
  params: {},
  navigate: (page, params = {}) => set({ currentPage: page, params }),
}));
