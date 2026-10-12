import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { authClient } from "../lib/auth-client.ts";
import { seedDevAdmin } from "../lib/api.ts";
import { Alert } from "../components/Alert.tsx";
import { Lock, Mail, Loader2, KeyRound } from "lucide-react";

export const Login: React.FC = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [devNotice, setDevNotice] = useState("");
  const [seeding, setSeeding] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setDevNotice("");

    if (!email || !password) {
      setError("Please enter both email and password.");
      return;
    }

    setLoading(true);

    try {
      const res = await authClient.signIn.email({
        email: email.trim(),
        password,
      });

      if (res.error) {
        setError(res.error.message || "Invalid email or password.");
        setLoading(false);
        return;
      }

      // Check if 2FA redirect is triggered
      if (res.data && "twoFactorRedirect" in res.data && res.data.twoFactorRedirect) {
        // MFA is enabled -> redirect to /mfa/verify
        navigate("/mfa/verify");
        return;
      }

      // If signed in, check if MFA is enabled on user profile
      const user = res.data?.user as { twoFactorEnabled?: boolean } | undefined;
      if (user && !user.twoFactorEnabled) {
        // MFA is not configured -> redirect to /mfa/setup
        // We pass password in navigation state so user doesn't have to re-enter it for twoFactor.enable
        navigate("/mfa/setup", { state: { password } });
      } else {
        // MFA is enabled and satisfied -> dashboard
        navigate("/dashboard");
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to sign in. Please check your credentials.";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const handleQuickSeedDevAdmin = async () => {
    setSeeding(true);
    setError("");
    setDevNotice("");

    try {
      const res = await seedDevAdmin();
      setDevNotice(res.message);
      setEmail("admin@example.com");
      setPassword("AdminDemo12345!Secure");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to initialize test admin.";
      setError(message);
    } finally {
      setSeeding(false);
    }
  };

  return (
    <div className="flex min-h-[calc(100vh-64px)] items-center justify-center p-4">
      <div className="w-full max-w-md rounded-xl border border-neutral-200 bg-white p-6 sm:p-8 shadow-sm">
        <div className="text-center mb-6">
          <div className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-neutral-900 text-white mb-3">
            <Lock className="h-6 w-6" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-neutral-900">Sign in to your account</h1>
          <p className="mt-1 text-sm text-neutral-500">
            Enter your credentials to test the MFA verification flow
          </p>
        </div>

        {error && (
          <div className="mb-4">
            <Alert type="error" message={error} />
          </div>
        )}

        {devNotice && (
          <div className="mb-4">
            <Alert type="success" message={devNotice} />
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-neutral-700 mb-1">
              Email address
            </label>
            <div className="relative">
              <Mail className="absolute left-3 top-3 h-4 w-4 text-neutral-400" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="admin@example.com"
                className="w-full rounded-lg border border-neutral-300 py-2.5 pl-10 pr-3 text-sm text-neutral-900 placeholder:text-neutral-400 focus:border-neutral-900 focus:outline-none focus:ring-2 focus:ring-neutral-900/10"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-neutral-700 mb-1">
              Password
            </label>
            <div className="relative">
              <KeyRound className="absolute left-3 top-3 h-4 w-4 text-neutral-400" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className="w-full rounded-lg border border-neutral-300 py-2.5 pl-10 pr-3 text-sm text-neutral-900 placeholder:text-neutral-400 focus:border-neutral-900 focus:outline-none focus:ring-2 focus:ring-neutral-900/10"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="flex w-full items-center justify-center rounded-lg bg-neutral-900 py-2.5 px-4 text-sm font-semibold text-white transition-colors hover:bg-neutral-800 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:ring-offset-2 disabled:bg-neutral-400 disabled:cursor-not-allowed"
          >
            {loading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Signing in...
              </>
            ) : (
              "LOGIN"
            )}
          </button>
        </form>

        {/* Development Helper Box */}
        <div className="mt-8 border-t border-neutral-200 pt-6">
          <div className="rounded-lg bg-neutral-50 p-4 border border-neutral-200 text-xs text-neutral-600">
            <p className="font-semibold text-neutral-900 mb-1">Local Development Test Admin:</p>
            <p className="mb-3">
              Need a test admin account? Click below to seed/reset the local development Admin (role: admin).
            </p>
            <button
              type="button"
              onClick={handleQuickSeedDevAdmin}
              disabled={seeding}
              className="inline-flex items-center rounded-md border border-neutral-300 bg-white px-3 py-1.5 font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50"
            >
              {seeding ? (
                <>
                  <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />
                  Seeding Admin...
                </>
              ) : (
                "Create / Reset Local Admin"
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
