export interface User {
  id: string;
  email: string;
  full_name: string;
  role: 'admin' | 'developer' | 'viewer';
  created_at: string;
}

export interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
}
