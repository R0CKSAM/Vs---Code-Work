import { DashboardResponse } from '../types/dashboard';
export const emptyDashboard: DashboardResponse = {
  system_status: { status: 'Unavailable', subtitle: 'Waiting for live data', current_date: '', last_updated: '', environment: 'Local' },
  kpis: { websites_monitored: 0, articles_today: 0, new_articles: 0, advertisements_tracked: 0,
    articles_change_pct: 0, new_articles_period: '', ads_change_pct: 0, articles_last_24h: 0,
    new_advertisements_24h: 0, updated_content_24h: 0, pages_checked_today: 0 },
  websites: [], latest_news: [], advertisements_summary: [],
};
