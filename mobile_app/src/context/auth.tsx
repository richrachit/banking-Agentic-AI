import { apiRequest, jsonBody } from '@/lib/api';
import { clearStoredSession, readStoredSession, writeStoredSession } from '@/lib/storage';
import type { AuthenticatedUser, Session, UserRole } from '@/lib/types';
import { createContext, PropsWithChildren, useCallback, useContext, useEffect, useMemo, useState } from 'react';

type LoginInput = { username: string; password: string; user_type: UserRole };
type SignupInput = LoginInput & { display_name: string; email: string };

type AuthContextValue = {
  session: Session | null;
  loading: boolean;
  login: (input: LoginInput) => Promise<void>;
  signup: (input: SignupInput) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    readStoredSession()
      .then((raw) => {
        if (!raw) return;
        try {
          const saved = JSON.parse(raw) as Session;
          if (saved.accessToken && saved.user?.role) setSession(saved);
        } catch {
          clearStoredSession().catch(() => undefined);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (input: LoginInput) => {
    const data = await apiRequest<{
      accessToken: string;
      user: AuthenticatedUser;
    }>('/api/v1/auth/login', { method: 'POST', ...jsonBody(input) });
    const next = { accessToken: data.accessToken, user: data.user };
    await writeStoredSession(JSON.stringify(next));
    setSession(next);
  }, []);

  const signup = useCallback(async (input: SignupInput) => {
    await apiRequest('/api/v1/auth/signup', { method: 'POST', ...jsonBody(input) });
  }, []);

  const logout = useCallback(async () => {
    const token = session?.accessToken;
    setSession(null);
    await clearStoredSession();
    if (token) {
      await apiRequest('/api/v1/auth/logout', { method: 'POST' }, token).catch(() => undefined);
    }
  }, [session?.accessToken]);

  const value = useMemo(() => ({ session, loading, login, signup, logout }), [session, loading, login, signup, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider.');
  return value;
}

