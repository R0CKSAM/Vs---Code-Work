import React from 'react';
import { Calendar, Clock, Activity, RefreshCw } from 'lucide-react';
import { SystemStatus } from '../../types/dashboard';
import { Badge } from '../common/Badge';

interface HeaderProps {
  systemStatus: SystemStatus;
  isLive: boolean;
  onRefresh?: () => void;
  isRefreshing?: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  systemStatus,
  isLive,
  onRefresh,
  isRefreshing = false,
}) => {
  return (
    <div className="dashboard-header">
      <div className="header-top">
        <div className="header-title-box">
          <h1>Media Reporting System</h1>
          <p>{systemStatus.subtitle}</p>
        </div>

        <div className="header-meta">
          <Badge variant="success" icon={<Activity size={12} />}>
            {systemStatus.status}
          </Badge>

          <div className="meta-item">
            <Calendar size={13} />
            <span>{systemStatus.current_date}</span>
          </div>

          <div className="meta-item">
            <Clock size={13} />
            <span>{systemStatus.last_updated}</span>
          </div>

          {onRefresh && (
            <button
              onClick={onRefresh}
              disabled={isRefreshing}
              title="Refresh Data from Backend"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
                padding: '4px 8px',
                background: 'var(--bg-surface-subtle)',
                border: '1px solid var(--border-light)',
                borderRadius: 'var(--radius-xs)',
                fontSize: '12px',
                color: 'var(--text-muted)',
              }}
            >
              <RefreshCw
                size={12}
                style={{
                  animation: isRefreshing ? 'spin 1s linear infinite' : 'none',
                }}
              />
              <span>Refresh</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
