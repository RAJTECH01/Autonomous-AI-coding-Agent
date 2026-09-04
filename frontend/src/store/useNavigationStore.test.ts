import { beforeEach, describe, expect, it } from 'vitest';
import { useNavigationStore } from './useNavigationStore';

describe('useNavigationStore', () => {
  beforeEach(() => {
    // Zustand stores are module singletons, so state survives between tests.
    // Reset explicitly or test order changes the result.
    useNavigationStore.setState({ currentPage: 'dashboard', params: {} });
  });

  it('starts on the dashboard with no params', () => {
    const { currentPage, params } = useNavigationStore.getState();
    expect(currentPage).toBe('dashboard');
    expect(params).toEqual({});
  });

  it('navigates to a page and records its params', () => {
    useNavigationStore.getState().navigate('project_details', { projectId: 'proj-agent-core' });

    const { currentPage, params } = useNavigationStore.getState();
    expect(currentPage).toBe('project_details');
    expect(params.projectId).toBe('proj-agent-core');
  });

  it('clears params from a previous navigation when none are supplied', () => {
    // Guards a real staleness bug: navigating away from a detail page and back
    // to a list must not leave the old projectId readable, or the next page can
    // render data for an entity the user is no longer looking at.
    useNavigationStore.getState().navigate('agent_execution', { runId: 'run-993' });
    expect(useNavigationStore.getState().params.runId).toBe('run-993');

    useNavigationStore.getState().navigate('projects');

    expect(useNavigationStore.getState().currentPage).toBe('projects');
    expect(useNavigationStore.getState().params).toEqual({});
  });

  it('replaces params rather than merging them', () => {
    useNavigationStore.getState().navigate('files', { projectId: 'p1', fileId: 'f1' });
    useNavigationStore.getState().navigate('files', { projectId: 'p2' });

    const { params } = useNavigationStore.getState();
    expect(params.projectId).toBe('p2');
    expect(params.fileId).toBeUndefined();
  });
});
