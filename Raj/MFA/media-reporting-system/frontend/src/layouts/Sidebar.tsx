import React from 'react';
import {
  LayoutDashboard,
  Globe,
  Newspaper,
  Megaphone,
  History,
  FileSpreadsheet,
  CalendarCheck,
  Sliders,
  Cpu,
  Settings,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { NavRoute } from '../types/dashboard';

interface SidebarProps {
  currentRoute: NavRoute;
  onNavigate: (route: NavRoute) => void;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentRoute,
  onNavigate,
  isCollapsed,
  onToggleCollapse,
}) => {
  const isRouteActive = (route: string) => {
    if (route === 'monitoring/websites' && currentRoute.startsWith('monitoring/websites')) {
      return true;
    }
    return currentRoute === route;
  };

  return (
    <aside
      className={`sidebar ${isCollapsed ? 'collapsed' : ''}`}
      style={{
        width: isCollapsed ? '68px' : 'var(--sidebar-width)',
        transition: 'width 0.2s ease',
      }}
    >
      {/* Brand Header */}
      <div className="sidebar-brand" style={{ justifyContent: isCollapsed ? 'center' : 'space-between', padding: isCollapsed ? '0' : '0 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div className="brand-icon">M</div>
          {!isCollapsed && (
            <div>
              <div className="brand-title">MediaIntel</div>
              <div className="brand-tag">Phase 1 • Enterprise</div>
            </div>
          )}
        </div>

        {!isCollapsed && (
          <button
            onClick={onToggleCollapse}
            style={{
              padding: '4px',
              borderRadius: 'var(--radius-xs)',
              color: 'var(--text-sidebar-muted)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            title="Collapse Sidebar"
          >
            <ChevronLeft size={16} />
          </button>
        )}
      </div>

      {isCollapsed && (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '10px 0' }}>
          <button
            onClick={onToggleCollapse}
            style={{
              padding: '6px',
              borderRadius: 'var(--radius-xs)',
              color: 'var(--text-sidebar-muted)',
              backgroundColor: 'var(--bg-sidebar-hover)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            title="Expand Sidebar"
          >
            <ChevronRight size={14} />
          </button>
        </div>
      )}

      {/* Navigation Groups */}
      <nav className="sidebar-nav" style={{ padding: isCollapsed ? '12px 6px' : '16px 12px' }}>
        {/* Overview */}
        <div>
          {!isCollapsed && <div className="nav-group-title">Overview</div>}
          <ul className="nav-list">
            <li>
              <button
                className={`nav-item-btn ${isRouteActive('dashboard') ? 'active' : ''}`}
                onClick={() => onNavigate('dashboard')}
                title="Dashboard"
              >
                <LayoutDashboard size={16} />
                {!isCollapsed && <span>Dashboard</span>}
              </button>
            </li>
          </ul>
        </div>

        {/* Monitoring */}
        <div>
          {!isCollapsed && <div className="nav-group-title">Monitoring</div>}
          <ul className="nav-list">
            <li>
              <button
                className={`nav-item-btn ${isRouteActive('monitoring/websites') ? 'active' : ''}`}
                onClick={() => onNavigate('monitoring/websites')}
                title="Websites Monitoring"
              >
                <Globe size={16} />
                {!isCollapsed && <span>Websites</span>}
              </button>
            </li>
            <li>
              <button
                className={`nav-item-btn ${isRouteActive('monitoring/news') ? 'active' : ''}`}
                onClick={() => onNavigate('monitoring/news')}
                title="News Monitoring"
              >
                <Newspaper size={16} />
                {!isCollapsed && <span>News</span>}
              </button>
            </li>
            <li>
              <button
                className={`nav-item-btn ${isRouteActive('monitoring/advertisements') ? 'active' : ''}`}
                onClick={() => onNavigate('monitoring/advertisements')}
                title="Advertisements Monitoring"
              >
                <Megaphone size={16} />
                {!isCollapsed && <span>Advertisements</span>}
              </button>
            </li>
            <li>
              <button
                className={`nav-item-btn ${isRouteActive('monitoring/changes') ? 'active' : ''}`}
                onClick={() => onNavigate('monitoring/changes')}
                title="Content Changes"
              >
                <History size={16} />
                {!isCollapsed && <span>Changes</span>}
              </button>
            </li>
          </ul>
        </div>

        {/* Reports */}
        <div>
          {!isCollapsed && <div className="nav-group-title">Reports</div>}
          <ul className="nav-list">
            <li>
              <button
                className={`nav-item-btn ${isRouteActive('reports/daily') ? 'active' : ''}`}
                onClick={() => onNavigate('reports/daily')}
                title="Daily Report"
              >
                <CalendarCheck size={16} />
                {!isCollapsed && <span>Daily Report</span>}
              </button>
            </li>
            <li>
              <button
                className={`nav-item-btn ${isRouteActive('reports/weekly') ? 'active' : ''}`}
                onClick={() => onNavigate('reports/weekly')}
                title="Weekly Report"
              >
                <FileSpreadsheet size={16} />
                {!isCollapsed && <span>Weekly Report</span>}
              </button>
            </li>
            <li>
              <button
                className={`nav-item-btn ${isRouteActive('reports/custom') ? 'active' : ''}`}
                onClick={() => onNavigate('reports/custom')}
                title="Custom Report"
              >
                <Sliders size={16} />
                {!isCollapsed && <span>Custom Report</span>}
              </button>
            </li>
          </ul>
        </div>

        {/* System */}
        <div>
          {!isCollapsed && <div className="nav-group-title">System</div>}
          <ul className="nav-list">
            <li>
              <button
                className={`nav-item-btn ${isRouteActive('system/scraper-status') ? 'active' : ''}`}
                onClick={() => onNavigate('system/scraper-status')}
                title="Scraper Status"
              >
                <Cpu size={16} />
                {!isCollapsed && <span>Scraper Status</span>}
              </button>
            </li>
            <li>
              <button
                className={`nav-item-btn ${isRouteActive('system/settings') ? 'active' : ''}`}
                onClick={() => onNavigate('system/settings')}
                title="System Settings"
              >
                <Settings size={16} />
                {!isCollapsed && <span>Settings</span>}
              </button>
            </li>
          </ul>
        </div>
      </nav>

      {/* Footer System Indicator */}
      <div className="sidebar-footer" style={{ padding: isCollapsed ? '12px 6px' : '14px 18px' }}>
        <div className="sidebar-status-box" style={{ justifyContent: isCollapsed ? 'center' : 'space-between' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center' }}>
            <span className="live-indicator"></span>
            {!isCollapsed && 'Engine Online'}
          </span>
          {!isCollapsed && <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10.5px' }}>v0.2.0</span>}
        </div>
      </div>
    </aside>
  );
};
