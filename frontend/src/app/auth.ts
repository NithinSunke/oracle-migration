import { useSyncExternalStore } from "react";

import { api } from "../services/api";

export interface AuthSession {
  user_id: string;
  username: string;
  authenticated_at: string;
  persistent: boolean;
}

const AUTH_STORAGE_KEY = "oracle-migration-auth-session";
const listeners = new Set<() => void>();
let cachedSession: AuthSession | null | undefined;

function emitChange() {
  listeners.forEach((listener) => listener());
}

function parseStoredSession(value: string | null): AuthSession | null {
  if (!value) {
    return null;
  }

  try {
    const parsed = JSON.parse(value) as Partial<AuthSession>;
    if (
      typeof parsed.user_id === "string" &&
      typeof parsed.username === "string" &&
      typeof parsed.authenticated_at === "string" &&
      typeof parsed.persistent === "boolean"
    ) {
      return {
        user_id: parsed.user_id,
        username: parsed.username,
        authenticated_at: parsed.authenticated_at,
        persistent: parsed.persistent,
      };
    }
  } catch {
    // Ignore corrupt stored sessions and fall back to unauthenticated state.
  }

  return null;
}

function readStoredSession(): AuthSession | null {
  return (
    parseStoredSession(window.localStorage.getItem(AUTH_STORAGE_KEY)) ??
    parseStoredSession(window.sessionStorage.getItem(AUTH_STORAGE_KEY))
  );
}

function getCachedSession(): AuthSession | null {
  if (cachedSession === undefined) {
    cachedSession = readStoredSession();
  }
  return cachedSession;
}

function writeStoredSession(session: AuthSession, persistent: boolean) {
  const serialized = JSON.stringify(session);
  if (persistent) {
    window.localStorage.setItem(AUTH_STORAGE_KEY, serialized);
    window.sessionStorage.removeItem(AUTH_STORAGE_KEY);
  } else {
    window.sessionStorage.setItem(AUTH_STORAGE_KEY, serialized);
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
  }
  cachedSession = session;
  emitChange();
}

function clearStoredSession() {
  window.localStorage.removeItem(AUTH_STORAGE_KEY);
  window.sessionStorage.removeItem(AUTH_STORAGE_KEY);
  cachedSession = null;
  emitChange();
}

export function subscribeToAuth(listener: () => void): () => void {
  listeners.add(listener);

  const handleStorage = (event: StorageEvent) => {
    if (event.key === AUTH_STORAGE_KEY) {
      cachedSession = readStoredSession();
      listener();
    }
  };

  window.addEventListener("storage", handleStorage);

  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", handleStorage);
  };
}

export function getAuthSession(): AuthSession | null {
  return getCachedSession();
}

export async function registerAccount(
  username: string,
  password: string,
  remember: boolean,
): Promise<AuthSession> {
  const normalizedUsername = username.trim();
  const normalizedPassword = password.trim();

  if (!normalizedUsername || !normalizedPassword) {
    throw new Error("Username and password are required.");
  }

  const session = await api.register({
    username: normalizedUsername,
    password: normalizedPassword,
    persistent: remember,
  });

  writeStoredSession(session, remember);
  return session;
}

export async function signIn(
  username: string,
  password: string,
  remember: boolean,
): Promise<AuthSession> {
  const normalizedUsername = username.trim();
  const normalizedPassword = password.trim();

  if (!normalizedUsername || !normalizedPassword) {
    throw new Error("Username and password are required.");
  }

  const session = await api.login({
    username: normalizedUsername,
    password: normalizedPassword,
    persistent: remember,
  });

  writeStoredSession(session, remember);
  return session;
}

export function signOut(): void {
  clearStoredSession();
}

export function useAuthSession(): AuthSession | null {
  return useSyncExternalStore(subscribeToAuth, getAuthSession, () => null);
}
