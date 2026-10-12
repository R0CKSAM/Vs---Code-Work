import React from 'react';
import { NavRoute } from '../types/dashboard';
import {
  Globe,
  Newspaper,
  Megaphone,
  History,
  FileSpreadsheet,
  CalendarCheck,
  Sliders,
  Cpu,
  Settings as SettingsIcon,
} from 'lucide-react';

interface PlaceholderPageProps {
  route: NavRoute;
  onBackToDashboard: () => void;
}

export const PlaceholderPage: React.FC<PlaceholderPageProps> = ({
  route,
  onBackToDashboard,
}) => {
  const getPageMeta = (r: NavRoute) => {
    switch (r) {
      case 'monitoring/websites':
        return {
          title: 'Websites Monitoring',
          icon: <Globe size={26} />,
          phase: 'Phase 2 & Phase 3 (Scrapers)',
          description:
            'Dedicated management console for adding and monitoring media portals (ET BrandEquity, Exchange4media, and upcoming news outlets).',
        };
      case 'monitoring/news':
        return {
          title: 'News Feed & Archival',
          icon: <Newspaper size={26} />,
          phase: 'Phase 4 (Database & History)',
          description:
            'Comprehensive real-time news archive with full-text search, editorial categorization, and sentiment tagging.',
        };
      case 'monitoring/advertisements':
        return {
          title: 'Advertisement Monitoring',
          icon: <Megaphone size={26} />,
          phase: 'Phase 6 (Advertisement Monitoring)',
          description:
            'Automated detection of programmatic banners, mastheads, sponsored articles, and advertiser placement logs with screenshot verification.',
        };
      case 'monitoring/changes':
        return {
          title: 'Content & Visual Change Detection',
          icon: <History size={26} />,
          phase: 'Phase 5 (Change Detection)',
          description:
            'Tracks DOM alterations, editorial headline edits, homepage layout shifts, and breaking news updates over time.',
        };
      case 'reports/daily':
        return {
          title: 'Daily Media Intelligence Brief',
          icon: <CalendarCheck size={26} />,
          phase: 'Phase 8 (Automated Reports)',
          description:
            'Automated morning and evening executive summaries exported as professional PDFs and Excel files.',
        };
      case 'reports/weekly':
        return {
          title: 'Weekly Industry Roll-up',
          icon: <FileSpreadsheet size={26} />,
          phase: 'Phase 8 (Automated Reports)',
          description:
            'Consolidated weekly analysis covering advertiser market share, top covered sectors, and brand campaign frequencies.',
        };
      case 'reports/custom':
        return {
          title: 'Custom Report Builder',
          icon: <Sliders size={26} />,
          phase: 'Phase 8 (Automated Reports)',
          description:
            'Configure parametric filters, date windows, and publication sets to export tailored media monitoring dossiers.',
        };
      case 'system/scraper-status':
        return {
          title: 'Scraper Engine Telemetry',
          icon: <Cpu size={26} />,
          phase: 'Phase 7 (Automated Scheduling)',
          description:
            'Health metrics, worker execution intervals, Playwright headless browser status, and proxy rotation logs.',
        };
      case 'system/settings':
        return {
          title: 'System Preferences & Configuration',
          icon: <SettingsIcon size={26} />,
          phase: 'Phase 0 — Foundation Configuration',
          description:
            'Configure local API endpoints, notification webhooks, export paths, and crawler intervals.',
        };
      default:
        return {
          title: 'Module Overview',
          icon: <Globe size={26} />,
          phase: 'Future Phase',
          description: 'This module is scheduled for development in upcoming project phases.',
        };
    }
  };

  const meta = getPageMeta(route);

  return (
    <div className="placeholder-container">
      <div className="placeholder-icon">{meta.icon}</div>
      <h2>{meta.title}</h2>
      <p>{meta.description}</p>
      <div style={{ marginBottom: '24px' }}>
        <span className="placeholder-badge">Scheduled for: {meta.phase}</span>
      </div>
      <div>
        <button
          onClick={onBackToDashboard}
          style={{
            padding: '8px 16px',
            backgroundColor: 'var(--accent-primary)',
            color: '#ffffff',
            borderRadius: 'var(--radius-sm)',
            fontSize: '13px',
            fontWeight: 500,
          }}
        >
          Return to Dashboard
        </button>
      </div>
    </div>
  );
};
