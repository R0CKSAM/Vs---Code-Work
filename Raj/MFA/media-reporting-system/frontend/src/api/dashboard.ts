import { apiFetch } from './client';
import { DashboardResponse, HealthResponse } from '../types/dashboard';
import { emptyDashboard } from '../data/emptyDashboard';
import { newsService } from '../services/newsService';
import { advertisementService } from '../services/advertisementService';

/**
 * Checks backend health status
 */
export async function fetchHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/health');
}

/**
 * Fetches dashboard data from FastAPI backend with an empty state if offline
 */
export async function fetchDashboardData(): Promise<{
  data: DashboardResponse;
  isLive: boolean;
  error?: string;
}> {
  try {
    const data = await apiFetch<DashboardResponse>('/dashboard');
    const [news, ads] = await Promise.all([newsService.getAllNews(), advertisementService.getAllAdvertisements()]);
    data.kpis = { ...emptyDashboard.kpis, ...data.kpis };
    data.latest_news = news.slice(0, 20);
    data.advertisements_summary = ads.slice(0, 5);
    data.websites = data.websites.map(site => ({
      ...site, new_articles: site.new_articles ?? 0,
      advertisements_detected: ads.filter(ad => ad.website === site.name).length,
      response_time_ms: site.response_time_ms ?? 0, changes_today: site.changes_today ?? 0,
    }));
    return { data, isLive: true };
  } catch (err: any) {
    console.warn('Backend unavailable, showing unavailable state:', err.message);
    return {
      data: emptyDashboard,
      isLive: false,
      error: err.message || 'Failed to connect to backend',
    };
  }
}
