"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { ApiError } from "./api";
import { auth as authApi } from "./endpoints";
import { homePathForRole, rolePresentation } from "./status";
import type { UserResponse } from "./types";

/**
 * Session state for a bearer-token API.
 *
 * The API issues a 60-minute JWT and offers no refresh and no cookie, so the
 * token lives in `localStorage` and is re-validated against `GET /auth/me` on
 * every page load. That validation is not redundant: it is the only thing that
 * can tell a stale token from a valid one, because there is no way to read the
 * expiry out of the token without verifying its signature.
 *
 * The consequence is that nothing renders until `isReady`. A guard that rendered
 * optimistically would flash the login screen for every signed-in user on every
 * navigation.
 *
 * A real deployment would put the token in an `HttpOnly` cookie and add a
 * refresh endpoint; neither exists on the server today, so neither is faked here.
 */

const TOKEN_KEY = "permitflow.token";
const ROLE_KEY = "permitflow.role";

interface Session {
  user: UserResponse | null;
  token: string | null;
  /** False until the stored token has been validated. Guards wait on this. */
  isReady: boolean;
  isAuthenticated: boolean;
  signIn: (email: string, password: string) => Promise<UserResponse>;
  signOut: () => void;
}

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<UserResponse | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isReady, setIsReady] = useState(false);

  /**
   * A 401 from any screen has to clear the session, or the user is left staring
   * at a permanently failing page with no way back to the login screen.
   */
  const clearSession = useCallback(() => {
    setUser(null);
    setToken(null);
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(ROLE_KEY);
  }, []);

  /**
   * Restore and validate on mount.
   *
   * Written as one async function rather than an early return plus a promise
   * chain so both the "no token" and "token present" paths end in the same place.
   * The `await` before the first state update is also what keeps these updates
   * out of the effect's synchronous body, which would otherwise mean committing
   * state mid-render-passthrough.
   */
  useEffect(() => {
    const controller = new AbortController();

    async function restore() {
      const stored = window.localStorage.getItem(TOKEN_KEY);

      if (!stored) {
        setIsReady(true);
        return;
      }

      setToken(stored);

      try {
        const identity = await authApi.me({ token: stored, signal: controller.signal });
        if (controller.signal.aborted) return;
        setUser(identity);
        // Prefer the server's role over the cached one: it is authoritative, and a
        // stale cached role would route the user to the wrong workspace.
        window.localStorage.setItem(ROLE_KEY, identity.role);
      } catch (error: unknown) {
        if (controller.signal.aborted) return;
        // An expired or revoked token, or an API that is merely down. Only the
        // former should log the user out; for the latter the token may still be
        // valid, so it is kept and the failure is left to surface per screen.
        if (error instanceof ApiError && error.isUnauthenticated) {
          clearSession();
        }
      } finally {
        if (!controller.signal.aborted) setIsReady(true);
      }
    }

    void restore();

    return () => controller.abort();
  }, [clearSession]);

  /**
   * Cross-tab logout. Signing out in one tab has to sign out the others, or a
   * shared workstation leaves a signed-in shell sitting in the next tab.
   */
  useEffect(() => {
    function onStorage(event: StorageEvent) {
      if (event.key === TOKEN_KEY && !event.newValue) {
        setUser(null);
        setToken(null);
        router.push("/login");
      }
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [router]);

  const signIn = useCallback(async (email: string, password: string) => {
    const result = await authApi.login(email, password);
    // `/auth/me` rather than trusting the login response, so the rest of the app
    // has one identity shape. The login response carries no email or agency id.
    const identity = await authApi.me({ token: result.access_token });

    window.localStorage.setItem(TOKEN_KEY, result.access_token);
    window.localStorage.setItem(ROLE_KEY, identity.role);
    setToken(result.access_token);
    setUser(identity);

    return identity;
  }, []);

  const signOut = useCallback(() => {
    clearSession();
    router.push("/login");
  }, [clearSession, router]);

  const value = useMemo<Session>(
    () => ({
      user,
      token,
      isReady,
      isAuthenticated: Boolean(user && token),
      signIn,
      signOut,
    }),
    [user, token, isReady, signIn, signOut],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) {
    throw new Error("useSession must be used inside a SessionProvider");
  }
  return session;
}

/**
 * The authenticated token, or throw.
 *
 * Screens below a guard render only when authenticated, so a missing token is a
 * programming error rather than a state to handle. Failing loudly beats a silent
 * `undefined` that turns into a confusing 401 three layers down.
 */
export function useToken(): string {
  const { token } = useSession();
  if (!token) throw new Error("useToken requires an authenticated session");
  return token;
}

export function useRoleLabel(): string {
  const { user } = useSession();
  return user ? rolePresentation(user.role).label : "";
}

/** Route a signed-in user to the workspace their role actually has. */
export function workspaceFor(role: UserResponse["role"]): string {
  return homePathForRole(role);
}