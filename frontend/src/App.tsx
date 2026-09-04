import React from 'react';
import { useNavigationStore, PageName } from './store/useNavigationStore';
import { Header } from './components/common/Header';
import { Sidebar } from './components/common/Sidebar';
import { ErrorBoundary } from './components/common/ErrorBoundary';

// Pages
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { DashboardPage } from './pages/DashboardPage';
import { ProjectsPage } from './pages/ProjectsPage';
import { ProjectDetailsPage } from './pages/ProjectDetailsPage';
import { NewCodingTaskPage } from './pages/NewCodingTaskPage';
import { AgentExecutionPage } from './pages/AgentExecutionPage';
import { FilesPage } from './pages/FilesPage';
import { TaskHistoryPage } from './pages/TaskHistoryPage';
import { AgentLogsPage } from './pages/AgentLogsPage';
import { SettingsPage } from './pages/SettingsPage';

export const App: React.FC = () => {
  const { currentPage } = useNavigationStore();

  const renderPage = (page: PageName) => {
    switch (page) {
      case 'login':
        return <LoginPage />;
      case 'register':
        return <RegisterPage />;
      case 'dashboard':
        return <DashboardPage />;
      case 'projects':
        return <ProjectsPage />;
      case 'project_details':
        return <ProjectDetailsPage />;
      case 'new_task':
        return <NewCodingTaskPage />;
      case 'agent_execution':
        return <AgentExecutionPage />;
      case 'files':
        return <FilesPage />;
      case 'task_history':
        return <TaskHistoryPage />;
      case 'agent_logs':
        return <AgentLogsPage />;
      case 'settings':
        return <SettingsPage />;
      default:
        return <DashboardPage />;
    }
  };

  const isAuthPage = currentPage === 'login' || currentPage === 'register';

  return (
    <>
      <div className="liquid-bg-container">
        <div className="liquid-blob liquid-blob-1"></div>
        <div className="liquid-blob liquid-blob-2"></div>
        <div className="liquid-blob liquid-blob-3"></div>
      </div>
      <div className="app-container">
        <Header />
        <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
          {!isAuthPage && <Sidebar />}
          <main className="main-content" style={{ flex: 1, overflowY: 'auto' }}>
            <ErrorBoundary>{renderPage(currentPage)}</ErrorBoundary>
          </main>
        </div>
      </div>
    </>
  );
};

export default App;
