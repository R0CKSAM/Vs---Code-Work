import { WebsiteInfo } from '../types/dashboard';
import { apiFetch } from '../api/client';
import { fetchDashboardData } from '../api/dashboard';
async function loadWebsites(): Promise<WebsiteInfo[]> {
  const result = await fetchDashboardData();
  if (!result.isLive) throw new Error(result.error || 'Live data unavailable');
  return result.data.websites;
}
export const websiteService = {
  getAllWebsites: loadWebsites,
  async getWebsiteById(id: string): Promise<WebsiteInfo | null> {
    return (await loadWebsites()).find(site => site.id === id) || null;
  },
  async triggerCheck(id: string): Promise<{success: boolean; message: string}> {
    const source = id === 'et-brandequity' ? 'et-brand-equity' : id;
    await apiFetch(`/monitoring/${source}/refresh`, {method: 'POST'});
    return {success: true, message: 'Live news and advertisement collection completed.'};
  },
};
