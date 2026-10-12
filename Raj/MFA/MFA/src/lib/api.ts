/**
 * API client helper to interact with protected backend endpoints.
 * Automatically sends session credentials/cookies.
 */

export interface DashboardDataResponse {
  status: string;
  welcomeMessage: string;
  user: {
    id: string;
    email: string;
    name: string;
    role: string;
    twoFactorEnabled: boolean;
  };
  authenticationStatus: {
    passwordVerified: boolean;
    mfaVerified: boolean;
  };
  serverTimestamp: string;
}

export interface SecurityStatusResponse {
  status: string;
  user: {
    id: string;
    email: string;
    name: string;
    role: string;
    twoFactorEnabled: boolean;
  };
}

export interface ApiError extends Error {
  status?: number;
  data?: Record<string, unknown>;
}

export async function fetchDashboardData(): Promise<DashboardDataResponse> {
  const response = await fetch("/api/protected/dashboard-data", {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "include",
  });

  let data: Record<string, unknown> = {};
  try {
    data = await response.json();
  } catch {
    // Non-JSON response fallback
  }

  if (!response.ok) {
    const message = (data?.message as string) || (data?.error as string) || `Request failed with status ${response.status}`;
    const error: ApiError = new Error(message);
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data as unknown as DashboardDataResponse;
}

export async function fetchSecurityStatus(): Promise<SecurityStatusResponse> {
  const response = await fetch("/api/protected/security-status", {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "include",
  });

  let data: Record<string, unknown> = {};
  try {
    data = await response.json();
  } catch {
    // Non-JSON response fallback
  }

  if (!response.ok) {
    const message = (data?.message as string) || (data?.error as string) || `Request failed with status ${response.status}`;
    const error: ApiError = new Error(message);
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data as unknown as SecurityStatusResponse;
}

export async function seedDevAdmin(password?: string): Promise<{ success: boolean; message: string }> {
  const response = await fetch("/api/dev/seed-admin", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ password }),
    credentials: "include",
  });

  let data: Record<string, unknown> = {};
  try {
    data = await response.json();
  } catch {
    // Non-JSON response fallback
  }

  if (!response.ok) {
    const message = (data?.message as string) || (data?.error as string) || `Failed to initialize Admin (status ${response.status})`;
    const error: ApiError = new Error(message);
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data as unknown as { success: boolean; message: string };
}
