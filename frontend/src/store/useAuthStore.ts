import { create } from 'zustand';
import { User } from '../types/auth';

interface AuthStoreState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  login: (email: string, token: string, user: User) => void;
  logout: () => void;
}

const SAVED_TOKEN = localStorage.getItem('auth_token');
const SAVED_USER = localStorage.getItem('auth_user');

export const useAuthStore = create<AuthStoreState>((set) => ({
  token: SAVED_TOKEN,
  user: SAVED_USER ? JSON.parse(SAVED_USER) : { id: 'u-101', email: 'dev@example.com', full_name: 'Lead Developer', role: 'developer', created_at: new Date().toISOString() },
  isAuthenticated: true, // Default active session for immediate productivity

  login: (email, token, user) => {
    localStorage.setItem('auth_token', token);
    localStorage.setItem('auth_user', JSON.stringify(user));
    set({ token, user, isAuthenticated: true });
  },

  logout: () => {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('auth_user');
    set({ token: null, user: null, isAuthenticated: false });
  },
}));
