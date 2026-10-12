/**
 * Reporting & Intelligence Dossier Types
 * Matches the FastAPI backend schemas from backend/reporting/report_models.py
 */

export interface ArticleReportItem {
  id: number;
  website_id: number;
  website_name: string;
  website_key: string;
  section_name: string;
  headline: string;
  url: string;
  image_url?: string | null;
  summary?: string | null;
  published_at?: string | null;
  first_seen_at: string;
  last_seen_at: string;
  last_changed_at: string;
  status: string;
  content_hash: string;
}

export interface PublisherBreakdown {
  website_name: string;
  website_key: string;
  article_count: number;
  percentage: number;
  new_count: number;
  updated_count: number;
  removed_count: number;
}

export interface SectionBreakdown {
  section_name: string;
  website_name: string;
  website_key: string;
  article_count: number;
  new_count: number;
  updated_count: number;
}

export interface DailyVolumeItem {
  date: string;
  et_count: number;
  e4m_count: number;
  total_count: number;
}

export interface MonitoringRunSummary {
  total_runs: number;
  successful_runs: number;
  failed_runs: number;
  last_run_time?: string | null;
  status_summary: string;
}

export interface ExecutiveSummary {
  reporting_date: string;
  total_articles: number;
  et_article_count: number;
  e4m_article_count: number;
  sections_count: number;
  new_articles_count: number;
  updated_articles_count: number;
  removed_articles_count: number;
  monitoring_status: string;
}

export interface DailyReportResponse {
  executive_summary: ExecutiveSummary;
  publisher_breakdown: PublisherBreakdown[];
  section_breakdown: SectionBreakdown[];
  top_stories: ArticleReportItem[];
  new_articles: ArticleReportItem[];
  updated_articles: ArticleReportItem[];
  removed_articles: ArticleReportItem[];
  monitoring_runs: MonitoringRunSummary;
}

export interface WeeklyReportResponse {
  date_range: {
    start_date: string;
    end_date: string;
  };
  total_articles: number;
  et_article_count: number;
  e4m_article_count: number;
  sections_count: number;
  new_articles_count: number;
  updated_articles_count: number;
  removed_articles_count: number;
  publisher_breakdown: PublisherBreakdown[];
  daily_volume: DailyVolumeItem[];
  section_breakdown: SectionBreakdown[];
  top_stories: ArticleReportItem[];
  new_articles: ArticleReportItem[];
  updated_articles: ArticleReportItem[];
  removed_articles: ArticleReportItem[];
  monitoring_runs: MonitoringRunSummary;
}

export interface CustomReportParams {
  start_date?: string;
  end_date?: string;
  website?: string;
  section?: string;
  status?: string;
  search?: string;
  limit?: number;
}

export interface CustomReportResponse {
  filters: Record<string, any>;
  total_matching: number;
  publisher_breakdown: PublisherBreakdown[];
  section_breakdown: SectionBreakdown[];
  status_breakdown: Record<string, number>;
  articles: ArticleReportItem[];
}

export type ExportFormat = 'pdf' | 'excel' | 'csv';
export type ExportReportType = 'daily' | 'weekly' | 'custom';

export interface ExportReportParams {
  report_type: ExportReportType;
  format: ExportFormat;
  date?: string;
  start_date?: string;
  end_date?: string;
  website?: string;
  section?: string;
  status?: string;
  search?: string;
}
