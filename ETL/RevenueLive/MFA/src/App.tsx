import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Navbar } from "./components/Navbar.tsx";
import { Login } from "./pages/Login.tsx";
import { MfaSetup } from "./pages/MfaSetup.tsx";
import { MfaVerify } from "./pages/MfaVerify.tsx";
import { Dashboard } from "./pages/Dashboard.tsx";
import { Security } from "./pages/Security.tsx";

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-neutral-50 text-neutral-900 flex flex-col">
        <Navbar />
        <main className="flex-1">
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/mfa/setup" element={<MfaSetup />} />
            <Route path="/mfa/verify" element={<MfaVerify />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/account/security" element={<Security />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
};
