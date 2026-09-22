import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { authClient } from "../lib/auth-client.ts";
import { fetchDashboardData, type DashboardDataResponse } from "../lib/api.ts";
import { Alert } from "../components/Alert.tsx";
import { ShieldCheck, CheckCircle2, KeyRound, LogOut, Loader2, UserCheck } from "lucide-react";

export const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardDataResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    let isMounted = true;

    async function loadDashboard() {
      setLoading(true);
      setError("");

      try {
        const res = await fetchDashboardData();
        if (isMounted) {
          setData(res);
        }
      } catch (err: unknown) {
        if (!isMounted) return;
        const apiErr = err as { status?: number; message?: string };
        const status = apiErr.status;
        const msg = apiErr.message || "Failed to load dashboard data.";

        if (status === 401 || msg.includes("401") || msg.includes("UNAUTHORIZED")) {
          navigate("/login");
          return;
        }

        if (status === 403 || msg.includes("403") || msg.includes("MFA_REQUIRED")) {
          // Password verified, but MFA setup incomplete
          navigate("/mfa/setup");
          return;
        }

        setError(msg);
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }

    loadDashboard();

    return () => {
      isMounted = false;
    };
  }, [navigate]);

  const handleLogout = async () => {
    try {
      await authClient.signOut();
    } catch {
      // ignore
    } finally {
      navigate("/login");
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-[calc(100vh-64px)] items-center justify-center p-4">
        <div className="flex flex-col items-center gap-3 text-neutral-500">
          <Loader2 className="h-8 w-8 animate-spin text-neutral-900" />
          <p className="text-sm">Verifying session and MFA status...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-[calc(100vh-64px)] items-center justify-center p-4">
      <div className="w-full max-w-lg rounded-xl border border-neutral-200 bg-white p-6 sm:p-8 shadow-sm">
        <div className="text-center mb-6">
          <div className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-600 text-white mb-3 shadow-xs">
            <ShieldCheck className="h-6 w-6" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-neutral-900">
            Secure MFA Demo
          </h1>
          <p className="mt-1 text-base font-medium text-neutral-700">
            Welcome, {data?.user?.name || "Admin"}
          </p>
        </div>

        {error && (
          <div className="mb-6">
            <Alert type="error" message={error} />
          </div>
        )}

        <div className="rounded-lg border border-neutral-200 bg-neutral-50 p-5 mb-6 space-y-4">
          <div>
            <h2 className="text-xs font-bold uppercase tracking-wider text-neutral-500 mb-2">
              Authentication Status
            </h2>
            <div className="space-y-2">
              <div className="flex items-center justify-between rounded-md bg-white p-2.5 border border-neutral-200 text-sm">
                <span className="font-medium text-neutral-700">Password:</span>
                <span className="inline-flex items-center gap-1 font-semibold text-emerald-700">
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                  Verified
                </span>
              </div>
              <div className="flex items-center justify-between rounded-md bg-white p-2.5 border border-neutral-200 text-sm">
                <span className="font-medium text-neutral-700">MFA:</span>
                <span className="inline-flex items-center gap-1 font-semibold text-emerald-700">
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                  Verified (TOTP)
                </span>
              </div>
            </div>
          </div>

          <div className="pt-2 border-t border-neutral-200">
            <h2 className="text-xs font-bold uppercase tracking-wider text-neutral-500 mb-2">
              Session Profile
            </h2>
            <div className="space-y-1.5 text-xs text-neutral-600">
              <div className="flex justify-between">
                <span className="text-neutral-500">Email:</span>
                <span className="font-mono font-medium text-neutral-900">{data?.user?.email}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Role:</span>
                <span className="inline-flex items-center gap-1 rounded bg-neutral-200 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-neutral-800 uppercase">
                  <UserCheck className="h-3 w-3" />
                  {data?.user?.role || "admin"}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row gap-3">
          <button
            type="button"
            onClick={() => navigate("/account/security")}
            className="flex flex-1 items-center justify-center gap-2 rounded-lg border border-neutral-300 bg-white py-2.5 px-4 text-sm font-semibold text-neutral-800 transition-colors hover:bg-neutral-50"
          >
            <KeyRound className="h-4 w-4" />
            Account Security
          </button>

          <button
            type="button"
            onClick={handleLogout}
            className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-neutral-900 py-2.5 px-4 text-sm font-semibold text-white transition-colors hover:bg-neutral-800"
          >
            <LogOut className="h-4 w-4" />
            Logout
          </button>
        </div>
      </div>
    </div>
  );
};
