import type { MiddlewareHandler } from "hono";
import { createAuth, type Env } from "./auth.ts";

export interface SessionUser {
  id: string;
  email: string;
  name: string;
  role?: string | null;
  twoFactorEnabled?: boolean | null;
  emailVerified?: boolean;
}

export interface SessionData {
  id: string;
  userId: string;
  expiresAt: Date;
  token: string;
  ipAddress?: string | null;
  userAgent?: string | null;
}

export interface AppContext {
  Bindings: Env;
  Variables: {
    auth: ReturnType<typeof createAuth>;
    user: SessionUser;
    session: SessionData;
  };
}

/**
 * Middleware: requireAuth
 * Verifies that the user has a valid, active Better Auth session.
 * Rejects with 401 Unauthorized if no session is present.
 */
export const requireAuth = (): MiddlewareHandler<AppContext> => {
  return async (c, next) => {
    const auth = createAuth(c.env);
    c.set("auth", auth);

    const sessionData = await auth.api.getSession({
      headers: c.req.raw.headers,
    });

    if (!sessionData || !sessionData.session || !sessionData.user) {
      return c.json(
        {
          error: "UNAUTHORIZED",
          message: "Authentication session required. Please log in.",
        },
        401
      );
    }

    c.set("user", sessionData.user as SessionUser);
    c.set("session", sessionData.session as SessionData);

    await next();
  };
};

/**
 * Middleware: requireMFA
 * Verifies that the user is authenticated AND has two-factor authentication (TOTP)
 * enabled and verified.
 * Rejects with 403 Forbidden if MFA is not enabled/completed.
 */
export const requireMFA = (): MiddlewareHandler<AppContext> => {
  return async (c, next) => {
    const auth = createAuth(c.env);
    c.set("auth", auth);

    const sessionData = await auth.api.getSession({
      headers: c.req.raw.headers,
    });

    if (!sessionData || !sessionData.session || !sessionData.user) {
      return c.json(
        {
          error: "UNAUTHORIZED",
          message: "Authentication session required. Please log in.",
        },
        401
      );
    }

    const user = sessionData.user as SessionUser;

    if (!user.twoFactorEnabled) {
      return c.json(
        {
          error: "MFA_REQUIRED",
          message:
            "Two-Factor Authentication is required to access this resource. Please complete MFA setup.",
          twoFactorEnabled: false,
        },
        403
      );
    }

    c.set("user", user);
    c.set("session", sessionData.session as SessionData);

    await next();
  };
};
