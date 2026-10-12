import React from 'react';

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'success' | 'info' | 'neutral';
  icon?: React.ReactNode;
}

export const Badge: React.FC<BadgeProps> = ({ children, variant = 'neutral', icon }) => {
  const variantClass = {
    success: 'badge-success',
    info: 'badge-info',
    neutral: 'badge-neutral',
  }[variant];

  return (
    <span className={`badge ${variantClass}`}>
      {icon}
      {children}
    </span>
  );
};
