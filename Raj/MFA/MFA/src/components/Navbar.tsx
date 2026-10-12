import React from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { authClient } from "../lib/auth-client.ts";
import { ShieldCheck, LogOut, KeyRound, LayoutDashboard } from "lucide-react";

export const Navbar: React.FC = () => {
  const { data: session } = authClient.useSession();
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = async () => {
    try {
      await authClient.signOut();
    } catch {
      // ignore
    } finally {
      navigate("/login");
    }
  };

  const isAuthPage =
    location.pathname === "/login" ||
    location.pathname === "/mfa/setup" ||
    location.pathname === "/mfa/verify";

  return (
    <header className="border-b border-neutral-200 bg-white shadow-sm">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3 sm:px-6">
        <Link to={session ? "/dashboard" : "/login"} className="flex items-center gap-2 font-semibold text-neutral-900">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-neutral-900 text-white">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <span>MFA Secure Demo</span>
        </Link>

        {session && !isAuthPage && (
          <nav className="flex items-center gap-4 text-sm font-medium">
            <Link
              to="/dashboard"
              className={`flex items-center gap-1.5 transition-colors ${
                location.pathname === "/dashboard"
                  ? "text-neutral-900 font-semibold"
                  : "text-neutral-600 hover:text-neutral-900"
              }`}
            >
              <LayoutDashboard className="h-4 w-4" />
              <span>Dashboard</span>
            </Link>

            <Link
              to="/account/security"
              className={`flex items-center gap-1.5 transition-colors ${
                location.pathname === "/account/security"
                  ? "text-neutral-900 font-semibold"
                  : "text-neutral-600 hover:text-neutral-900"
              }`}
            >
              <KeyRound className="h-4 w-4" />
              <span>Security</span>
            </Link>

            <button
              onClick={handleLogout}
              className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-neutral-600 transition-colors hover:bg-neutral-100 hover:text-neutral-900"
            >
              <LogOut className="h-4 w-4" />
              <span>Logout</span>
            </button>
          </nav>
        )}
      </div>
    </header>
  );
};
