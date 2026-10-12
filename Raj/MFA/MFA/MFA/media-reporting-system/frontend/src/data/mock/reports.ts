import { DailyReportSummary, WeeklyReportSummary } from '../../types/dashboard';
import { mockNewsArticles } from './news';

export const mockDailyReport: DailyReportSummary = {
  report_date: 'Wednesday, September 23, 2026',
  total_news: 48,
  new_articles: 12,
  advertisements_count: 34,
  major_changes_count: 7,
  top_stories: mockNewsArticles.slice(0, 4),
  executive_takeaways: [
    'Connected TV (CTV) allocation among FMCG advertisers accelerated by 35% across regional vernacular content hubs.',
    'Consortium of top Indian broadcasters initiated formal standardizations for unified cross-screen reach measurement.',
    'Samsung and Tata Motors dominated premium masthead and high-impact video inventory across both tracked portals.',
    'Quick-commerce retail media ad networks are demonstrating 40% YoY expansion, outcompeting standard display programmatic.',
  ],
};

export const mockWeeklyReport: WeeklyReportSummary = {
  week_range: 'Sep 17, 2026 – Sep 23, 2026',
  total_news: 312,
  total_ads: 218,
  total_changes: 54,
  brand_share: [
    { brand: 'Samsung Electronics', share_pct: 24.5, count: 53 },
    { brand: 'Tata Motors EV', share_pct: 19.2, count: 42 },
    { brand: 'Amazon India', share_pct: 16.8, count: 37 },
    { brand: 'Swiggy Instamart', share_pct: 14.1, count: 31 },
    { brand: 'HDFC Bank', share_pct: 11.4, count: 25 },
    { brand: 'Google Cloud India', share_pct: 8.3, count: 18 },
    { brand: 'Others (Long Tail)', share_pct: 5.7, count: 12 },
  ],
  website_comparison: [
    {
      website: 'ET BrandEquity',
      articles: 178,
      ads: 124,
      changes: 32,
      uptime_pct: 99.8,
    },
    {
      website: 'Exchange4media',
      articles: 134,
      ads: 94,
      changes: 22,
      uptime_pct: 99.6,
    },
  ],
  top_stories: mockNewsArticles.slice(0, 5),
};
