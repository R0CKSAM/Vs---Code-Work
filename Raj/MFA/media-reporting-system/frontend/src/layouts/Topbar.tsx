import React from 'react';
import { Search, Wifi, WifiOff, Bell, RefreshCw } from 'lucide-react';
import { NavRoute } from '../types/dashboard';

interface TopbarProps {
  currentRoute: NavRoute;
  isLive: boolean;
  onOpenCommandPalette: () => void;
  onRefreshData?: () => void;
  isRefreshing?: boolean;
}

export const Topbar: React.FC<TopbarProps> = ({
  currentRoute,
  isLive,
  onOpenCommandPalette,
  onRefreshData,
  isRefreshing = false,
}) => {
  const getPageInfo = (route: NavRoute) => {
    if (route.startsWith('monitoring/websites/')) {
      return {
        title: 'Website Deep-Dive',
        desc: 'Detailed portal telemetry and asset inventory',
      };
    }

    switch (route) {
      case 'dashboard':
        return {
          title: 'Media Reporting System',
          desc: 'Media intelligence & competitive tracking dashboard',
        };
      case 'monitoring/websites':
        return {
          title: 'Monitored Publications',
          desc: 'Portals indexed for news, ads, and layout tracking',
        };
      case 'monitoring/news':
        return {
          title: 'News Intelligence Feed',
          desc: 'Live verified headlines and editorial content changes',
        };
      case 'monitoring/advertisements':
        return {
          title: 'Advertisement Intelligence',
          desc: 'Campaign placements, brand tracking, and format telemetry',
        };
      case 'monitoring/changes':
        return {
          title: 'Content Diff Audit Log',
          desc: 'Historical modification stream across all publications',
        };
      case 'reports/daily':
        return {
          title: 'Daily Media Intelligence Brief',
          desc: 'Morning and evening consolidated executive summaries',
        };
      case 'reports/weekly':
        return {
          title: 'Weekly Industry Roll-up',
          desc: 'Multi-day trendlines, share of voice, and publisher comparison',
        };
      case 'reports/custom':
        return {
          title: 'Custom Report Dossier',
          desc: 'Parametric multi-source report compiler',
        };
      case 'system/scraper-status':
        return {
          title: 'Scraper Engine Telemetry',
          desc: 'Worker health, latency metrics, and scheduler queues',
        };
      case 'system/settings':
        return {
          title: 'System Preferences',
          desc: 'Local crawling cadence, thresholds, and notifications',
        };
      default:
        return {
          title: 'Media Reporting System',
          desc: 'Media intelligence platform',
        };
    }
  };

  const info = getPageInfo(currentRoute);

  return (
    <header className="topbar">
      {/* Left: Route Title and Description */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1px' }}>
        <h1 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-main)', lineHeight: 1.2 }}>
          {info.title}
        </h1>
        <span style={{ fontSize: '11.5px', color: 'var(--text-muted)' }}>{info.desc}</span>
      </div>

      {/* Center: Command Palette Trigger Button */}
      <div style={{ flex: 1, maxWidth: '420px', margin: '0 24px' }}>
        <button
          onClick={onOpenCommandPalette}
          style={{
            width: '100%',
            height: '36px',
            backgroundColor: 'var(--bg-surface-subtle)',
            border: '1px solid var(--border-light)',
            borderRadius: 'var(--radius-sm)',
            padding: '0 12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '12.5px',
            color: 'var(--text-muted)',
            cursor: 'pointer',
          }}
          title="Open global search (Ctrl+K or ⌘K)"
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Search size={14} color="var(--text-subtle)" />
            <span>Search articles, advertisers, brands, campaigns...</span>
          </div>
          <span
            style={{
              fontSize: '11px',
              fontFamily: 'var(--font-mono)',
              padding: '2px 5px',
              backgroundColor: '#ffffff',
              border: '1px solid var(--border-light)',
              borderRadius: 'var(--radius-xs)',
              color: 'var(--text-muted)',
            }}
          >
            Ctrl+K
          </span>
        </button>
      </div>

      {/* Right Controls */}
      <div className="topbar-right">
        {/* Refresh Action */}
        {onRefreshData && (
          <button
            onClick={onRefreshData}
            disabled={isRefreshing}
            style={{
              padding: '6px 10px',
              borderRadius: 'var(--radius-xs)',
              border: '1px solid var(--border-light)',
              backgroundColor: 'var(--bg-surface-subtle)',
              fontSize: '12px',
              color: 'var(--text-main)',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
            }}
            title="Poll FastAPI backend for fresh metrics"
          >
            <RefreshCw
              size={12}
              style={{ animation: isRefreshing ? 'spin 1s linear infinite' : 'none' }}
            />
            <span style={{ fontSize: '11.5px' }}>Sync</span>
          </button>
        )}

        {/* Connection status pill */}
        <div className={`connection-pill ${isLive ? 'conn-live' : 'conn-mock'}`}>
          {isLive ? (
            <>
              <Wifi size={12} />
              <span>FastAPI Connected</span>
            </>
          ) : (
            <>
              <WifiOff size={12} />
              <span>Mock Mode</span>
            </>
          )}
        </div>

        {/* Notifications Icon Placeholder */}
        <button
          style={{
            position: 'relative',
            width: '32px',
            height: '32px',
            borderRadius: 'var(--radius-xs)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-muted)',
            border: '1px solid var(--border-light)',
            backgroundColor: 'var(--bg-surface-subtle)',
          }}
          title="Notifications"
        >
          <Bell size={14} />
          <span
            style={{
              position: 'absolute',
              top: '6px',
              right: '7px',
              width: '6px',
              height: '6px',
              backgroundColor: '#0284c7',
              borderRadius: '50%',
            }}
          />
        </button>

        {/* User / Workspace profile */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            paddingLeft: '6px',
            borderLeft: '1px solid var(--border-light)',
          }}
        >
          <div
            style={{
              width: '30px',
              height: '30px',
              borderRadius: 'var(--radius-xs)',
              backgroundColor: '#0f172a',
              color: '#ffffff',
              fontSize: '11.5px',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            MR
          </div>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, lineHeight: 1.1 }}>Enterprise Admin</span>
            <span style={{ fontSize: '10.5px', color: 'var(--text-muted)' }}>Phase 1 Workspace</span>
          </div>
        </div>
      </div>
    </header>
  );
};
