import React, { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { QRCodeSVG } from "qrcode.react";
import { authClient } from "../lib/auth-client.ts";
import { OtpInput } from "../components/OtpInput.tsx";
import { Alert } from "../components/Alert.tsx";
import { ShieldCheck, Copy, Check, Loader2, KeyRound } from "lucide-react";

export const MfaSetup: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();

  // Retrieve password if passed from login redirect state
  const statePassword = (location.state as { password?: string })?.password || "";
  const [password, setPassword] = useState(statePassword);
  const [needsPasswordPrompt, setNeedsPasswordPrompt] = useState(!statePassword);

  const [totpURI, setTotpURI] = useState<string>("");
  const [backupCodes, setBackupCodes] = useState<string[]>([]);
  const [code, setCode] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [verifying, setVerifying] = useState<boolean>(false);
  const [error, setError] = useState<string>("");
  const [copied, setCopied] = useState<boolean>(false);
  const [setupStep, setSetupStep] = useState<"init" | "qr" | "codes">("init");

  // If password was passed via state, auto-enable 2FA to get TOTP URI
  useEffect(() => {
    if (statePassword) {
      handleInitiateSetup(statePassword);
    }
  }, [statePassword]);

  const handleInitiateSetup = async (pwdToUse: string) => {
    if (!pwdToUse) {
      setError("Password confirmation is required to enable MFA.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const res = await authClient.twoFactor.enable({
        password: pwdToUse,
      });

      if (res.error) {
        setError(res.error.message || "Failed to initiate MFA setup.");
        setNeedsPasswordPrompt(true);
        setLoading(false);
        return;
      }

      if (res.data) {
        // Better Auth returns totpURI and backupCodes
        const uri = res.data.totpURI;
        const codes = res.data.backupCodes || [];

        if (!uri) {
          setError("Failed to retrieve TOTP URI from authentication server.");
          setLoading(false);
          return;
        }

        setTotpURI(uri);
        setBackupCodes(codes);
        setNeedsPasswordPrompt(false);
        setSetupStep("qr");
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Error initiating 2FA setup.";
      setError(message);
      setNeedsPasswordPrompt(true);
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async (codeOverride?: string) => {
    const codeToVerify = codeOverride || code;
    if (codeToVerify.length !== 6) {
      setError("Please enter the complete 6-digit code.");
      return;
    }

    setVerifying(true);
    setError("");

    try {
      const res = await authClient.twoFactor.verifyTotp({
        code: codeToVerify,
      });

      if (res.error) {
        setError(res.error.message || "Invalid authentication code. Please try again.");
        setVerifying(false);
        return;
      }

      // Successful verification! Show recovery codes step
      setSetupStep("codes");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to verify authenticator code.";
      setError(message);
    } finally {
      setVerifying(false);
    }
  };

  const copyRecoveryCodes = () => {
    const textToCopy = backupCodes.join("\n");
    navigator.clipboard.writeText(textToCopy);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  return (
    <div className="flex min-h-[calc(100vh-64px)] items-center justify-center p-4">
      <div className="w-full max-w-lg rounded-xl border border-neutral-200 bg-white p-6 sm:p-8 shadow-sm">
        {/* Step 1: Password confirmation (if not already provided in state) */}
        {needsPasswordPrompt && setupStep === "init" && (
          <div>
            <div className="text-center mb-6">
              <div className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-neutral-900 text-white mb-3">
                <KeyRound className="h-6 w-6" />
              </div>
              <h1 className="text-2xl font-bold tracking-tight text-neutral-900">
                Confirm Password to Setup MFA
              </h1>
              <p className="mt-1 text-sm text-neutral-500">
                To protect your account, please confirm your current password before configuring Two-Factor Authentication.
              </p>
            </div>

            {error && (
              <div className="mb-4">
                <Alert type="error" message={error} />
              </div>
            )}

            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleInitiateSetup(password);
              }}
              className="space-y-4"
            >
              <div>
                <label className="block text-sm font-medium text-neutral-700 mb-1">
                  Current Password
                </label>
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full rounded-lg border border-neutral-300 py-2.5 px-3 text-sm text-neutral-900 focus:border-neutral-900 focus:outline-none focus:ring-2 focus:ring-neutral-900/10"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="flex w-full items-center justify-center rounded-lg bg-neutral-900 py-2.5 px-4 text-sm font-semibold text-white transition-colors hover:bg-neutral-800 disabled:bg-neutral-400"
              >
                {loading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Generating TOTP Secret...
                  </>
                ) : (
                  "Continue Setup"
                )}
              </button>
            </form>
          </div>
        )}

        {/* Step 2: QR Code and OTP verification */}
        {setupStep === "qr" && (
          <div>
            <div className="text-center mb-6">
              <div className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-neutral-900 text-white mb-3">
                <ShieldCheck className="h-6 w-6" />
              </div>
              <h1 className="text-2xl font-bold tracking-tight text-neutral-900">
                Enable Two-Factor Authentication
              </h1>
              <p className="mt-1 text-sm text-neutral-500">
                Scan this QR code using your authenticator app (Google Authenticator, 1Password, Bitwarden, etc.)
              </p>
            </div>

            {error && (
              <div className="mb-4">
                <Alert type="error" message={error} />
              </div>
            )}

            {/* Offline local QR Code rendering */}
            <div className="my-6 flex flex-col items-center justify-center">
              <div className="rounded-xl border border-neutral-200 bg-white p-4 shadow-sm">
                <QRCodeSVG
                  value={totpURI}
                  size={200}
                  level="M"
                  includeMargin={false}
                />
              </div>
              <p className="mt-3 text-xs text-neutral-400">
                Rendered offline directly in browser. No third-party APIs used.
              </p>
            </div>

            <div className="mt-6 text-center">
              <label className="block text-sm font-medium text-neutral-700 mb-1">
                Then enter the 6-digit code:
              </label>
              <OtpInput
                value={code}
                onChange={setCode}
                onComplete={(completedCode) => handleVerify(completedCode)}
                disabled={verifying}
              />
            </div>

            <button
              type="button"
              onClick={handleVerify}
              disabled={verifying || code.length !== 6}
              className="mt-6 flex w-full items-center justify-center rounded-lg bg-neutral-900 py-2.5 px-4 text-sm font-semibold text-white transition-colors hover:bg-neutral-800 disabled:bg-neutral-400 disabled:cursor-not-allowed"
            >
              {verifying ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Verifying Code...
                </>
              ) : (
                "VERIFY & ENABLE MFA"
              )}
            </button>
          </div>
        )}

        {/* Step 3: Display Recovery Codes */}
        {setupStep === "codes" && (
          <div>
            <div className="text-center mb-6">
              <div className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-600 text-white mb-3">
                <Check className="h-6 w-6" />
              </div>
              <h1 className="text-2xl font-bold tracking-tight text-neutral-900">
                Save your Recovery Codes
              </h1>
              <p className="mt-1 text-sm text-neutral-500">
                Store these somewhere safe. If you lose access to your authenticator app, each code can be used once to access your account.
              </p>
            </div>

            <div className="my-6 rounded-lg border border-neutral-200 bg-neutral-50 p-4">
              <div className="grid grid-cols-2 gap-2 text-center font-mono text-sm font-bold text-neutral-800">
                {backupCodes.map((backupCode, i) => (
                  <div
                    key={i}
                    className="rounded border border-neutral-200 bg-white py-2 px-3 tracking-wider shadow-xs"
                  >
                    {backupCode}
                  </div>
                ))}
              </div>

              <div className="mt-4 flex justify-end">
                <button
                  type="button"
                  onClick={copyRecoveryCodes}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-neutral-700 hover:text-neutral-900"
                >
                  {copied ? (
                    <>
                      <Check className="h-3.5 w-3.5 text-emerald-600" />
                      <span>Copied to clipboard</span>
                    </>
                  ) : (
                    <>
                      <Copy className="h-3.5 w-3.5" />
                      <span>Copy All Codes</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            <p className="text-xs text-neutral-500 text-center mb-6">
              Do NOT share your recovery codes. A recovery code works only once.
            </p>

            <button
              type="button"
              onClick={() => navigate("/dashboard")}
              className="flex w-full items-center justify-center rounded-lg bg-neutral-900 py-2.5 px-4 text-sm font-semibold text-white transition-colors hover:bg-neutral-800"
            >
              I HAVE SAVED THEM
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
