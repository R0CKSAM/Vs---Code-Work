import { DashboardResponse } from '../types/dashboard';
import { fetchDashboardData } from '../api/dashboard';
import { emptyDashboard } from '../data/emptyDashboard';

export const dashboardService = {
  async getDashboard(): Promise<{ data: DashboardResponse; isLive: boolean; error?: string }> {
    try {
      const res = await fetchDashboardData();
      return res;
    } catch {
      return {
        data: emptyDashboard,
        isLive: false,
      };
    }
  },
};
