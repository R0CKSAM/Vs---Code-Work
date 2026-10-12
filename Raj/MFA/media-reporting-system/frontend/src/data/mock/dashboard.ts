import { DashboardResponse } from '../../types/dashboard';
import { mockWebsites } from './websites';
import { mockNewsArticles } from './news';
import { mockAdvertisements } from './advertisements';

export const mockDashboardData: DashboardResponse = {
  system_status: {
    status: 'Monitoring Active',
    subtitle: 'Enterprise media monitoring & competitive intelligence dashboard',
    current_date: 'Wednesday, September 23, 2026',
    last_updated: 'Today at 12:35 IST',
    environment: 'Local Workstation (Phase 1 UI)',
  },
  kpis: {
    websites_monitored: 2,
    articles_today: 48,
    new_articles: 12,
    advertisements_tracked: 34,
    articles_change_pct: 14.5,
    new_articles_period: 'in last 2 hours',
    ads_change_pct: 8.2,
    // Second-row intelligence metrics
    articles_last_24h: 112,
    new_advertisements_24h: 9,
    updated_content_24h: 16,
    pages_checked_today: 144,
  },
  websites: mockWebsites,
  latest_news: mockNewsArticles,
  advertisements_summary: mockAdvertisements,
};
