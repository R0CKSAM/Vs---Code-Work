import { Hono } from "hono";
import { cors } from "hono/cors";
import { createAuth, type Env } from "./auth.ts";
import { requireAuth, requireMFA, type AppContext } from "./middleware.ts";
import { getDb } from "./db.ts";
import * as schema from "../db/schema.ts";
import { eq } from "drizzle-orm";

const app = new Hono<AppContext>();

// CORS configuration for local development & SPA communication
app.use(
  "/api/*",
  cors({
    origin: (origin) => {
      // Allow localhost and 127.0.0.1 on ports 5173 and 8787
      if (!origin || origin.includes("localhost") || origin.includes("127.0.0.1")) {
        return origin || "http://localhost:5173";
      }
      return origin;
    },
    credentials: true,
    allowMethods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allowHeaders: ["Content-Type", "Authorization", "Cookie"],
  })
);

// 1. Better Auth catch-all API handler
app.on(["GET", "POST"], "/api/auth/*", (c) => {
  const auth = createAuth(c.env);
  return auth.handler(c.req.raw);
});

// 2. Protected Dashboard Endpoint (Requires active session AND completed MFA)
app.get("/api/protected/dashboard-data", requireMFA(), (c) => {
  const user = c.get("user");
  return c.json({
    status: "ok",
    welcomeMessage: `Welcome, ${user.name || "Admin"}`,
    user: {
      id: user.id,
      email: user.email,
      name: user.name,
      role: user.role || "admin",
      twoFactorEnabled: user.twoFactorEnabled,
    },
    authenticationStatus: {
      passwordVerified: true,
      mfaVerified: true,
    },
    serverTimestamp: new Date().toISOString(),
  });
});

// 3. Protected Account Security Endpoint (Requires active session)
app.get("/api/protected/security-status", requireAuth(), (c) => {
  const user = c.get("user");
  return c.json({
    status: "ok",
    user: {
      id: user.id,
      email: user.email,
      name: user.name,
      role: user.role || "admin",
      twoFactorEnabled: !!user.twoFactorEnabled,
    },
  });
});

// 4. Safe Development-Only Admin Seed Endpoint
// This endpoint is only enabled when ENVIRONMENT !== 'production'.
app.post("/api/dev/seed-admin", async (c) => {
  if (c.env.ENVIRONMENT === "production") {
    return c.json(
      { error: "FORBIDDEN", message: "Dev seed endpoint is disabled in production." },
      403
    );
  }

  const auth = createAuth(c.env);
  const db = getDb(c.env.DB);

  let email = c.env.ADMIN_DEFAULT_EMAIL || "admin@example.com";
  let password = c.env.ADMIN_DEFAULT_PASSWORD || "AdminDemo12345!Secure";

  // Allow passing custom email/password in request body for local testing
  try {
    const body = await c.req.json().catch(() => ({}));
    if (body.email) email = body.email;
    if (body.password) password = body.password;
  } catch {
    // default to env vars
  }

  // Check if admin already exists
  const existingUsers = await db
    .select()
    .from(schema.user)
    .where(eq(schema.user.email, email))
    .limit(1);

  if (existingUsers.length > 0) {
    const existing = existingUsers[0];

    // Cleanly delete user and cascading relations (sessions, accounts, twoFactor)
    await db.delete(schema.twoFactor).where(eq(schema.twoFactor.userId, existing.id));
    await db.delete(schema.session).where(eq(schema.session.userId, existing.id));
    await db.delete(schema.account).where(eq(schema.account.userId, existing.id));
    await db.delete(schema.user).where(eq(schema.user.id, existing.id));

    // Now re-create fresh test admin user via Better Auth
    const created = await auth.api.signUpEmail({
      body: {
        email,
        password,
        name: "Admin User",
      },
    });

    if (created && created.user) {
      await db
        .update(schema.user)
        .set({ role: "admin", twoFactorEnabled: false })
        .where(eq(schema.user.id, created.user.id));
    }

    return c.json({
      success: true,
      action: "reset",
      email,
      role: "admin",
      mfaReset: true,
      message:
        "Existing Admin user was safely reset. MFA is disabled; you can now log in and test initial MFA setup.",
    });
  }

  // Create new Admin user using Better Auth API
  try {
    const created = await auth.api.signUpEmail({
      body: {
        email,
        password,
        name: "Admin User",
      },
    });

    if (created && created.user) {
      // Explicitly set role = 'admin'
      await db
        .update(schema.user)
        .set({ role: "admin" })
        .where(eq(schema.user.id, created.user.id));
    }

    return c.json({
      success: true,
      action: "created",
      email,
      role: "admin",
      message:
        "Test Admin account created successfully with role = admin. Use these credentials to test the login flow.",
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return c.json(
      {
        error: "CREATION_FAILED",
        message: `Failed to create test admin: ${message}`,
      },
      500
    );
  }
});

// Fallback health route
app.get("/api/health", (c) => {
  return c.json({ status: "healthy", service: "mfa-demo-worker" });
});

export default app;
