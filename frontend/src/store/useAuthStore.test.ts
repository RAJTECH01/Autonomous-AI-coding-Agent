import { beforeEach, describe, expect, it } from 'vitest';
import { useAuthStore } from './useAuthStore';
import type { User } from '../types/auth';

const USER: User = {
  id: 'u-1',
  email: 'engineer@example.com',
  full_name: 'Test Engineer',
  role: 'developer',
  created_at: new Date().toISOString(),
};

describe('useAuthStore', () => {
  beforeEach(() => {
    localStorage.clear();
    useAuthStore.setState({ token: null, user: null, isAuthenticated: false });
  });

  it('persists the token and user on login', () => {
    useAuthStore.getState().login(USER.email, 'jwt-token-value', USER);

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.token).toBe('jwt-token-value');
    expect(state.user?.email).toBe(USER.email);

    expect(localStorage.getItem('auth_token')).toBe('jwt-token-value');
    expect(JSON.parse(localStorage.getItem('auth_user') ?? '{}').id).toBe('u-1');
  });

  it('clears both state and localStorage on logout', () => {
    useAuthStore.getState().login(USER.email, 'jwt-token-value', USER);
    useAuthStore.getState().logout();

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.token).toBeNull();
    expect(state.user).toBeNull();

    // A token left behind in localStorage after logout is a real security bug:
    // the next page load would rehydrate the session.
    expect(localStorage.getItem('auth_token')).toBeNull();
    expect(localStorage.getItem('auth_user')).toBeNull();
  });

  it('round-trips the user through JSON without losing fields', () => {
    useAuthStore.getState().login(USER.email, 't', USER);

    const stored = JSON.parse(localStorage.getItem('auth_user') as string);
    expect(stored).toEqual(USER);
  });
});
