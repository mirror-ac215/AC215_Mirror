import { useEffect, useSyncExternalStore } from "react";

export type Role = "patient" | "clinician";

export interface AuthenticatedUser {
  user_id: string;
  role: Role;
}

let authenticatedUser: AuthenticatedUser | null = null;
const listeners = new Set<() => void>();

function notify(): void {
  if (typeof document !== "undefined") {
    document.documentElement.dataset["role"] = authenticatedUser?.role ?? "anonymous";
  }
  listeners.forEach((listener) => listener());
}

/** Store only the identity returned by the authenticated gateway response. */
export function setAuthenticatedUser(user: AuthenticatedUser): void {
  authenticatedUser = user;
  notify();
}

/** Clear the in-memory identity whenever the bearer token is discarded. */
export function clearAuthenticatedUser(): void {
  authenticatedUser = null;
  notify();
}

export function getAuthenticatedUser(): AuthenticatedUser | null {
  return authenticatedUser;
}

/** Return true only when the gateway-authenticated identity has the requested role. */
export function hasRequiredRole(role: Role): boolean {
  return authenticatedUser?.role === role;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useAuthenticatedUser(): AuthenticatedUser | null {
  const user = useSyncExternalStore(subscribe, getAuthenticatedUser, () => null);
  useEffect(notify, [user]);
  return user;
}
