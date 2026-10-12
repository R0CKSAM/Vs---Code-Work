import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { authClient } from "../lib/auth-client.ts";
import { OtpInput } from "../components/OtpInput.tsx";
import { Alert } from "../components/Alert.tsx";
import { ShieldAlert, KeyRound, Loader2, Smartphone } from "lucide-react";

export const MfaVerify: React.FC = () => {
  const navigate = useNavigate();
  const [useRecoveryCode, setUseRecoveryCode] = useState<boolean>(false);
  const [totpCode, setTotpCode] = useState<string>("");
  const [recoveryCode, setRecoveryCode] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>("");

  const handleVerifyTotp = async (codeToVerify?: string) => {
    const code = codeToVerify || totpCode;
    if (code.length !== 6) {
      setError("Please enter the 6-digit code.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const res = await authClient.twoFactor.verifyTotp({
        code,
      });

      if (res.error) {
        setError("Invalid authentication code.");
        setLoading(false);
        return;
      }

      // Successful verification
      navigate("/dashboard");
    } catch {
      setError("Invalid authentication code.");
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyRecoveryCode = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanCode = recoveryCode.trim();
    if (!cleanCode) {
      setError("Please enter a recovery code.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const res = await authClient.twoFactor.verifyBackupCode({
        code: cleanCode,
      });

      if (res.error) {
        setError("Invalid authentication code.");
        setLoading(false);
        return;
      }

      // Successful recovery code verification
      navigate("/dashboard");
    } catch {
      setError("Invalid authentication code.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-[calc(100vh-64px)] items-center justify-center p-4">
      <div className="w-full max-w-md rounded-xl border border-neutral-200 bg-white p-6 sm:p-8 shadow-sm">
        <div className="text-center mb-6">
          <div className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-neutral-900 text-white mb-3">
            {useRecoveryCode ? (
              <KeyRound className="h-6 w-6" />
            ) : (
              <ShieldAlert className="h-6 w-6" />
            )}
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-neutral-900">
            Security Verification
          </h1>
          <p className="mt-1 text-sm text-neutral-500">
            {useRecoveryCode
              ? "Enter one of your emergency recovery backup codes."
              : "Enter the 6-digit code from your authenticator app."}
          </p>
        </div>

        {error && (
          <div className="mb-4">
            <Alert type="error" message={error} />
          </div>
        )}

        {!useRecoveryCode ? (
          <div>
            <OtpInput
              value={totpCode}
              onChange={setTotpCode}
              onComplete={(completedCode) => handleVerifyTotp(completedCode)}
              disabled={loading}
            />

            <button
              type="button"
              onClick={() => handleVerifyTotp()}
              disabled={loading || totpCode.length !== 6}
              className="mt-6 flex w-full items-center justify-center rounded-lg bg-neutral-900 py-2.5 px-4 text-sm font-semibold text-white transition-colors hover:bg-neutral-800 disabled:bg-neutral-400 disabled:cursor-not-allowed"
            >
              {loading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Verifying...
                </>
              ) : (
                "VERIFY"
              )}
            </button>

            <div className="mt-6 text-center">
              <button
                type="button"
                onClick={() => {
                  setError("");
                  setUseRecoveryCode(true);
                }}
                className="text-xs font-semibold text-neutral-600 hover:text-neutral-900 transition-colors"
              >
                Use Recovery Code
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleVerifyRecoveryCode} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-neutral-700 mb-1">
                Backup Recovery Code
              </label>
              <input
                type="text"
                required
                value={recoveryCode}
                onChange={(e) => setRecoveryCode(e.target.value)}
                placeholder="e.g. ABCD-1234"
                className="w-full rounded-lg border border-neutral-300 py-2.5 px-3 font-mono text-center text-base tracking-widest text-neutral-900 uppercase focus:border-neutral-900 focus:outline-none focus:ring-2 focus:ring-neutral-900/10"
              />
              <p className="mt-1.5 text-xs text-neutral-400 text-center">
                Each recovery code can only be used once.
              </p>
            </div>

            <button
              type="submit"
              disabled={loading || !recoveryCode.trim()}
              className="flex w-full items-center justify-center rounded-lg bg-neutral-900 py-2.5 px-4 text-sm font-semibold text-white transition-colors hover:bg-neutral-800 disabled:bg-neutral-400 disabled:cursor-not-allowed"
            >
              {loading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Verifying Recovery Code...
                </>
              ) : (
                "VERIFY WITH RECOVERY CODE"
              )}
            </button>

            <div className="mt-4 text-center">
              <button
                type="button"
                onClick={() => {
                  setError("");
                  setUseRecoveryCode(false);
                }}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-neutral-600 hover:text-neutral-900 transition-colors"
              >
                <Smartphone className="h-3.5 w-3.5" />
                <span>Use Authenticator App code</span>
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
