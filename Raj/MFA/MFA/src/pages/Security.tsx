import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { authClient } from "../lib/auth-client.ts";
import { fetchSecurityStatus, type SecurityStatusResponse } from "../lib/api.ts";
import { Alert } from "../components/Alert.tsx";
import {
  KeyRound,
  Shield,
  ShieldAlert,
  ShieldCheck,
  RefreshCw,
  LogOut,
  Loader2,
  Copy,
  Check,
  X,
} from "lucide-react";

export const Security: React.FC = () => {
  const navigate = useNavigate();
  const [data, setData] = useState<SecurityStatusResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");
  const [successMsg, setSuccessMsg] = useState<string>("");

  // Modals state
  const [showRegenModal, setShowRegenModal] = useState<boolean>(false);
  const [showDisableModal, setShowDisableModal] = useState<boolean>(false);
  const [actionPassword, setActionPassword] = useState<string>("");
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [modalError, setModalError] = useState<string>("");

  // New recovery codes modal state
  const [newBackupCodes, setNewBackupCodes] = useState<string[]>([]);
  const [copiedCodes, setCopiedCodes] = useState<boolean>(false);

  useEffect(() => {
    loadSecurityData();
  }, []);

  const loadSecurityData = async () => {
    setLoading(true);
    setError("");

    try {
      const res = await fetchSecurityStatus();
      setData(res);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load security status.";
      if (msg.includes("401") || msg.includes("UNAUTHORIZED")) {
        navigate("/login");
        return;
      }
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleRegenerateCodes = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!actionPassword) {
      setModalError("Password is required to regenerate recovery codes.");
      return;
    }

    setActionLoading(true);
    setModalError("");

    try {
      const res = await authClient.twoFactor.generateBackupCodes({
        password: actionPassword,
      });

      if (res.error) {
        setModalError(res.error.message || "Failed to regenerate recovery codes.");
        setActionLoading(false);
        return;
      }

      if (res.data && res.data.backupCodes) {
        setNewBackupCodes(res.data.backupCodes);
        setShowRegenModal(false);
        setActionPassword("");
        setSuccessMsg("Recovery codes have been successfully regenerated.");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to regenerate recovery codes.";
      setModalError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  const handleDisableMfa = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!actionPassword) {
      setModalError("Password confirmation is required to disable MFA.");
      return;
    }

    setActionLoading(true);
    setModalError("");

    try {
      const res = await authClient.twoFactor.disable({
        password: actionPassword,
      });

      if (res.error) {
        setModalError(res.error.message || "Failed to disable MFA.");
        setActionLoading(false);
        return;
      }

      setShowDisableModal(false);
      setActionPassword("");
      setSuccessMsg("Two-Factor Authentication has been disabled.");
      await loadSecurityData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to disable MFA.";
      setModalError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  const handleLogoutAllSessions = async () => {
    setLoading(true);
    try {
      await authClient.revokeSessions();
      await authClient.signOut();
    } catch {
      // ignore
    } finally {
      navigate("/login");
    }
  };

  const copyCodes = () => {
    navigator.clipboard.writeText(newBackupCodes.join("\n"));
    setCopiedCodes(true);
    setTimeout(() => setCopiedCodes(false), 2000);
  };

  if (loading && !data) {
    return (
      <div className="flex min-h-[calc(100vh-64px)] items-center justify-center p-4">
        <div className="flex flex-col items-center gap-3 text-neutral-500">
          <Loader2 className="h-8 w-8 animate-spin text-neutral-900" />
          <p className="text-sm">Loading security settings...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-[calc(100vh-64px)] items-center justify-center p-4">
      <div className="w-full max-w-lg rounded-xl border border-neutral-200 bg-white p-6 sm:p-8 shadow-sm">
        <div className="text-center mb-6">
          <div className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-neutral-900 text-white mb-3 shadow-xs">
            <KeyRound className="h-6 w-6" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-neutral-900">
            Account Security
          </h1>
          <p className="mt-1 text-sm text-neutral-500">
            Manage your two-factor authentication and security credentials
          </p>
        </div>

        {error && (
          <div className="mb-4">
            <Alert type="error" message={error} />
          </div>
        )}

        {successMsg && (
          <div className="mb-4">
            <Alert type="success" message={successMsg} />
          </div>
        )}

        {/* Security Overview */}
        <div className="rounded-lg border border-neutral-200 bg-neutral-50 p-5 mb-6 space-y-3">
          <div className="flex items-center justify-between text-sm py-1 border-b border-neutral-200">
            <span className="text-neutral-600 font-medium">Email</span>
            <span className="font-mono text-neutral-900 font-semibold">{data?.user.email}</span>
          </div>

          <div className="flex items-center justify-between text-sm py-1 border-b border-neutral-200">
            <span className="text-neutral-600 font-medium">Role</span>
            <span className="inline-flex items-center rounded bg-neutral-200 px-2 py-0.5 font-mono text-xs font-semibold uppercase text-neutral-800">
              {data?.user.role || "Admin"}
            </span>
          </div>

          <div className="flex items-center justify-between text-sm py-1 border-b border-neutral-200">
            <span className="text-neutral-600 font-medium">Two-Factor Authentication</span>
            {data?.user.twoFactorEnabled ? (
              <span className="inline-flex items-center gap-1 font-semibold text-emerald-700 text-xs bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                <ShieldCheck className="h-3.5 w-3.5" />
                Enabled
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 font-semibold text-neutral-600 text-xs bg-neutral-200 px-2 py-0.5 rounded">
                <ShieldAlert className="h-3.5 w-3.5" />
                Disabled
              </span>
            )}
          </div>

          <div className="flex items-center justify-between text-sm py-1">
            <span className="text-neutral-600 font-medium">Recovery Codes</span>
            <span className="text-xs font-semibold text-neutral-700 bg-white px-2 py-0.5 rounded border border-neutral-200">
              {data?.user.twoFactorEnabled ? "Available" : "Not Configured"}
            </span>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="space-y-3">
          {data?.user.twoFactorEnabled ? (
            <>
              <button
                type="button"
                onClick={() => {
                  setActionPassword("");
                  setModalError("");
                  setShowRegenModal(true);
                }}
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-neutral-300 bg-white py-2.5 px-4 text-sm font-semibold text-neutral-800 transition-colors hover:bg-neutral-50"
              >
                <RefreshCw className="h-4 w-4" />
                Regenerate Recovery Codes
              </button>

              <button
                type="button"
                onClick={() => {
                  setActionPassword("");
                  setModalError("");
                  setShowDisableModal(true);
                }}
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-red-200 bg-red-50 py-2.5 px-4 text-sm font-semibold text-red-700 transition-colors hover:bg-red-100"
              >
                <ShieldAlert className="h-4 w-4" />
                Disable MFA
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={() => navigate("/mfa/setup")}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-neutral-900 py-2.5 px-4 text-sm font-semibold text-white transition-colors hover:bg-neutral-800"
            >
              <Shield className="h-4 w-4" />
              Configure & Enable MFA
            </button>
          )}

          <button
            type="button"
            onClick={handleLogoutAllSessions}
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-neutral-300 bg-white py-2.5 px-4 text-sm font-semibold text-neutral-700 transition-colors hover:bg-neutral-50 hover:text-neutral-900"
          >
            <LogOut className="h-4 w-4" />
            Logout All Sessions
          </button>
        </div>

        <div className="mt-6 text-center">
          <button
            type="button"
            onClick={() => navigate("/dashboard")}
            className="text-xs font-semibold text-neutral-500 hover:text-neutral-900"
          >
            ← Back to Dashboard
          </button>
        </div>
      </div>

      {/* Modal: Regenerate Recovery Codes Password Confirmation */}
      {showRegenModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-lg">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-neutral-900">
                Regenerate Recovery Codes
              </h3>
              <button
                onClick={() => setShowRegenModal(false)}
                className="text-neutral-400 hover:text-neutral-600"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <p className="text-sm text-neutral-600 mb-4">
              Regenerating recovery codes will invalidate all previous backup codes. Please enter your password to confirm.
            </p>

            {modalError && (
              <div className="mb-4">
                <Alert type="error" message={modalError} />
              </div>
            )}

            <form onSubmit={handleRegenerateCodes} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-neutral-700 mb-1">
                  Current Password
                </label>
                <input
                  type="password"
                  required
                  value={actionPassword}
                  onChange={(e) => setActionPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full rounded-lg border border-neutral-300 py-2 px-3 text-sm text-neutral-900 focus:border-neutral-900 focus:outline-none focus:ring-2 focus:ring-neutral-900/10"
                />
              </div>

              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setShowRegenModal(false)}
                  className="flex-1 rounded-lg border border-neutral-300 py-2 text-sm font-semibold text-neutral-700 hover:bg-neutral-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading || !actionPassword}
                  className="flex-1 rounded-lg bg-neutral-900 py-2 text-sm font-semibold text-white hover:bg-neutral-800 disabled:bg-neutral-400"
                >
                  {actionLoading ? "Regenerating..." : "Regenerate"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Display Newly Generated Recovery Codes */}
      {newBackupCodes.length > 0 && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-lg">
            <h3 className="text-lg font-bold text-neutral-900 text-center mb-2">
              New Recovery Codes Generated
            </h3>
            <p className="text-xs text-neutral-500 text-center mb-4">
              Previous recovery codes are now void. Save these new single-use codes in a safe place.
            </p>

            <div className="rounded-lg border border-neutral-200 bg-neutral-50 p-4 mb-4">
              <div className="grid grid-cols-2 gap-2 text-center font-mono text-xs font-bold text-neutral-800">
                {newBackupCodes.map((code, i) => (
                  <div key={i} className="rounded border border-neutral-200 bg-white py-1.5 px-2">
                    {code}
                  </div>
                ))}
              </div>
              <div className="mt-3 text-right">
                <button
                  type="button"
                  onClick={copyCodes}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-neutral-700 hover:text-neutral-900"
                >
                  {copiedCodes ? (
                    <>
                      <Check className="h-3 w-3 text-emerald-600" />
                      <span>Copied</span>
                    </>
                  ) : (
                    <>
                      <Copy className="h-3 w-3" />
                      <span>Copy All</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            <button
              type="button"
              onClick={() => setNewBackupCodes([])}
              className="w-full rounded-lg bg-neutral-900 py-2.5 text-sm font-semibold text-white hover:bg-neutral-800"
            >
              I Have Saved These Codes
            </button>
          </div>
        </div>
      )}

      {/* Modal: Disable MFA Confirmation */}
      {showDisableModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-lg">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-red-600">
                Disable Two-Factor Authentication
              </h3>
              <button
                onClick={() => setShowDisableModal(false)}
                className="text-neutral-400 hover:text-neutral-600"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <p className="text-sm text-neutral-600 mb-4">
              Disabling MFA reduces the security of your account. To proceed, please confirm your current password.
            </p>

            {modalError && (
              <div className="mb-4">
                <Alert type="error" message={modalError} />
              </div>
            )}

            <form onSubmit={handleDisableMfa} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-neutral-700 mb-1">
                  Current Password
                </label>
                <input
                  type="password"
                  required
                  value={actionPassword}
                  onChange={(e) => setActionPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full rounded-lg border border-neutral-300 py-2 px-3 text-sm text-neutral-900 focus:border-neutral-900 focus:outline-none focus:ring-2 focus:ring-neutral-900/10"
                />
              </div>

              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setShowDisableModal(false)}
                  className="flex-1 rounded-lg border border-neutral-300 py-2 text-sm font-semibold text-neutral-700 hover:bg-neutral-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading || !actionPassword}
                  className="flex-1 rounded-lg bg-red-600 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:bg-red-300"
                >
                  {actionLoading ? "Disabling..." : "Confirm & Disable"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
