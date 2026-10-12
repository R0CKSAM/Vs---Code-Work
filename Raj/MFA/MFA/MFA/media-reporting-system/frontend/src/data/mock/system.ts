import { ScraperStatusItem, SystemSettings } from '../../types/dashboard';

export const mockScraperStatus: ScraperStatusItem[] = [
  {
    id: 'scraper-et',
    name: 'ET BrandEquity Collector',
    url: 'https://brandequity.economictimes.indiatimes.com/',
    status: 'SUCCESS',
    last_run: '3 minutes ago (12:28 IST)',
    duration_sec: 4.8,
    articles_found: 28,
    ads_found: 19,
    errors_count: 0,
    next_run: 'in 7 minutes (12:38 IST)',
    frequency: 'Every 10 minutes',
    mode: 'Requests + BeautifulSoup (Scheduled for Phase 2)',
  },
  {
    id: 'scraper-e4m',
    name: 'Exchange4media Collector',
    url: 'https://www.exchange4media.com/',
    status: 'SUCCESS',
    last_run: '5 minutes ago (12:26 IST)',
    duration_sec: 5.2,
    articles_found: 20,
    ads_found: 15,
    errors_count: 0,
    next_run: 'in 5 minutes (12:36 IST)',
    frequency: 'Every 10 minutes',
    mode: 'Playwright Headless Browser (Scheduled for Phase 3)',
  },
];

export const defaultSystemSettings: SystemSettings = {
  monitoring_interval_minutes: 10,
  default_website: 'all',
  default_date_range: 'today',
  enable_notifications: true,
  enable_sound_alerts: false,
  retention_days: 30,
  crawler_concurrency: 2,
};
