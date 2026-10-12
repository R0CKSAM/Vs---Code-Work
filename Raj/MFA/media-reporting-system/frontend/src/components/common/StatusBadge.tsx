import React from 'react';

interface StatusBadgeProps {
  status: string;
  size?: 'sm' | 'md';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, size = 'md' }) => {
  const normalized = status.toUpperCase();

  let bg = '#f1f5f9';
  let color = '#475569';
  let border = '#cbd5e1';

  if (normalized === 'ONLINE' || normalized === 'ACTIVE' || normalized === 'SUCCESS') {
    bg = '#ecfdf5';
    color = '#047857';
    border = '#a7f3d0';
  } else if (normalized === 'NEW') {
    bg = '#eff6ff';
    color = '#1d4ed8';
    border = '#bfdbfe';
  } else if (normalized === 'CHANGED' || normalized === 'UPDATED' || normalized === 'WARNING') {
    bg = '#fffbeb';
    color = '#b45309';
    border = '#fde68a';
  } else if (normalized === 'REMOVED' || normalized === 'OFFLINE' || normalized === 'ERROR') {
    bg = '#fef2f2';
    color = '#b91c1c';
    border = '#fecaca';
  } else if (normalized === 'UNCHANGED' || normalized === 'IDLE') {
    bg = '#f8fafc';
    color = '#64748b';
    border = '#e2e8f0';
  }

  const padding = size === 'sm' ? '2px 6px' : '3px 8px';
  const fontSize = size === 'sm' ? '11px' : '11.5px';

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        padding,
        backgroundColor: bg,
        color,
        border: `1px solid ${border}`,
        borderRadius: '3px',
        fontSize,
        fontWeight: 600,
        letterSpacing: '0.4px',
        lineHeight: 1.1,
        whiteSpace: 'nowrap',
      }}
    >
      <span
        style={{
          width: '5px',
          height: '5px',
          borderRadius: '50%',
          backgroundColor: color,
        }}
      />
      {status}
    </span>
  );
};
