export type SystemStatusType = 'ONLINE' | 'WARNING' | 'OFFLINE' | 'NOT CHECKED';
export type NewsStatusType = 'NEW' | 'UPDATED' | 'UNCHANGED';
export type AdStatusType = 'NEW' | 'ACTIVE' | 'CHANGED' | 'REMOVED';
export type ChangeType = 'NEW ARTICLE' | 'ARTICLE UPDATED' | 'NEW AD' | 'AD CHANGED' | 'AD REMOVED';

export interface SystemStatus {
  status: string;
  subtitle: string;
  current_date: string;
  last_updated: string;
  environment: string;
}

export interface KPIData {
  websites_monitored: number;
  articles_today: number;
  new_articles: number;
  advertisements_tracked: number;
  articles_change_pct: number;
  new_articles_period: string;
  ads_change_pct: number;
  // Second-row intelligence metrics
  articles_last_24h: number;
  new_advertisements_24h: number;
  updated_content_24h: number;
  pages_checked_today: number;
}

export interface WebsiteInfo {
  id: string;
  name: string;
  url: string;
  status: SystemStatusType;
  last_checked: string;
  articles_detected: number;
  new_articles: number;
  advertisements_detected: number;
  domain: string;
  category: string;
  response_time_ms: number;
  changes_today: number;
}

export interface ArticleChangeHistory {
  timestamp: string;
  field: string;
  old_value: string;
  new_value: string;
}

export interface NewsArticle {
  id: string;
  headline: string;
  summary: string;
  source: string;
  source_id: string;
  section: string;
  published_time: string;
  first_seen: string;
  last_seen: string;
  status: NewsStatusType;
  image_url?: string | null;
  url: string;
  read_time: string;
  author?: string;
  content_hash: string;
  change_history?: ArticleChangeHistory[];
}

export interface AdTimelineEvent {
  stage: string;
  timestamp: string;
  description: string;
}

export interface Advertisement {
  id: string;
  advertiser?: string | null;
  brand?: string | null;
  campaign?: string | null;
  website: string;
  website_id: string;
  section_page: string;
  page_url?: string;
  position: string;
  ad_type?: string;
  image_url?: string | null;
  local_image_path?: string | null;
  target_url?: string | null;
  ad_hash?: string;
  first_seen: string;
  last_seen: string;
  first_seen_at?: string;
  last_seen_at?: string;
  status: AdStatusType;
  screenshot_url?: string;
  previous_screenshot_url?: string;
  format: string;
  timeline?: AdTimelineEvent[];
}

export interface ContentChange {
  id: string;
  timestamp: string;
  website: string;
  website_id: string;
  type: ChangeType;
  item: string;
  change_description: string;
  status: 'ACTIVE' | 'ARCHIVED' | 'INVESTIGATING';
  item_id: string;
}

export interface ScraperStatusItem {
  id: string;
  name: string;
  url: string;
  status: 'IDLE' | 'RUNNING' | 'SUCCESS' | 'WARNING' | 'ERROR';
  last_run: string;
  duration_sec: number;
  articles_found: number;
  ads_found: number;
  errors_count: number;
  next_run: string;
  frequency: string;
  mode: string;
}

export interface DailyReportSummary {
  report_date: string;
  total_news: number;
  new_articles: number;
  advertisements_count: number;
  major_changes_count: number;
  top_stories: NewsArticle[];
  executive_takeaways: string[];
}

export interface WeeklyReportSummary {
  week_range: string;
  total_news: number;
  total_ads: number;
  total_changes: number;
  brand_share: { brand: string; share_pct: number; count: number }[];
  website_comparison: {
    website: string;
    articles: number;
    ads: number;
    changes: number;
    uptime_pct: number;
  }[];
  top_stories: NewsArticle[];
}

export interface SystemSettings {
  monitoring_interval_minutes: number;
  default_website: string;
  default_date_range: string;
  enable_notifications: boolean;
  enable_sound_alerts: boolean;
  retention_days: number;
  crawler_concurrency: number;
}

export interface DashboardResponse {
  system_status: SystemStatus;
  kpis: KPIData;
  websites: WebsiteInfo[];
  latest_news: NewsArticle[];
  advertisements_summary: Advertisement[];
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  phase: string;
}

export type NavRoute =
  | 'dashboard'
  | 'monitoring/websites'
  | 'monitoring/websites/:websiteId'
  | 'monitoring/news'
  | 'monitoring/advertisements'
  | 'monitoring/changes'
  | 'reports/daily'
  | 'reports/weekly'
  | 'reports/custom'
  | 'system/scraper-status'
  | 'system/settings';
