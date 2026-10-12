import React from "react";
import { AlertCircle, CheckCircle2, Info } from "lucide-react";

interface AlertProps {
  type?: "error" | "success" | "info";
  message: string;
}

export const Alert: React.FC<AlertProps> = ({ type = "error", message }) => {
  if (!message) return null;

  const styles = {
    error: "bg-red-50 text-red-800 border-red-200",
    success: "bg-emerald-50 text-emerald-800 border-emerald-200",
    info: "bg-neutral-100 text-neutral-800 border-neutral-200",
  };

  const icons = {
    error: <AlertCircle className="h-4 w-4 shrink-0 text-red-600" />,
    success: <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />,
    info: <Info className="h-4 w-4 shrink-0 text-neutral-600" />,
  };

  return (
    <div
      className={`flex items-center gap-2 rounded-lg border p-3 text-sm transition-all ${styles[type]}`}
      role="alert"
    >
      {icons[type]}
      <span className="leading-snug">{message}</span>
    </div>
  );
};
