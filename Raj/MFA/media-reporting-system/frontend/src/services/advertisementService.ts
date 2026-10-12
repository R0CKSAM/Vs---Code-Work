import { Advertisement } from '../types/dashboard';
import { apiFetch, API_BASE_URL } from '../api/client';

interface ApiAdvertisementItem {
  id: number;
  website_id: number;
  website_name?: string | null;
  website_key?: string | null;
  section_name?: string | null;
  page_url: string;
  advertiser?: string | null;
  brand?: string | null;
  campaign?: string | null;
  ad_type: string;
  position: string;
  image_url?: string | null;
  local_image_path?: string | null;
  target_url?: string | null;
  ad_hash: string;
  first_seen_at: string;
  last_seen_at: string;
  status: string;
  removed_at?: string | null;
}

interface ApiAdvertisementsResponse {
  count: number;
  total: number;
  kpis: {
    total_ads: number;
    active_ads: number;
    removed_ads: number;
    changed_ads: number;
    unique_advertisers: number;
    unique_brands: number;
  };
  advertisements: ApiAdvertisementItem[];
}

function mapApiAdToModel(a: ApiAdvertisementItem): Advertisement {
  const backendBase = API_BASE_URL.replace(/\/api\/?$/, '');
  const screenshot = a.local_image_path
    ? `${backendBase}/${a.local_image_path.replace(/\\/g, '/')}`
    : a.image_url || undefined;

  const websiteDisplayName =
    a.website_name || (a.website_key === 'et_brand_equity' ? 'ET BrandEquity' : 'Exchange4media');

  return {
    id: String(a.id),
    advertiser: a.advertiser || null,
    brand: a.brand || null,
    campaign: a.campaign || null,
    website: websiteDisplayName,
    website_id: a.website_key || String(a.website_id),
    section_page: a.section_name || 'Homepage',
    page_url: a.page_url,
    position: a.position,
    ad_type: a.ad_type,
    image_url: a.image_url,
    local_image_path: a.local_image_path,
    target_url: a.target_url,
    ad_hash: a.ad_hash,
    first_seen: a.first_seen_at ? a.first_seen_at.replace('T', ' ').slice(0, 16) : 'Unknown',
    last_seen: a.last_seen_at ? a.last_seen_at.replace('T', ' ').slice(0, 16) : 'Unknown',
    first_seen_at: a.first_seen_at,
    last_seen_at: a.last_seen_at,
    status: (a.status as any) || 'ACTIVE',
    screenshot_url: screenshot,
    format: a.ad_type,
    timeline: [
      {
        stage: 'First Observed',
        timestamp: a.first_seen_at ? a.first_seen_at.replace('T', ' ').slice(0, 16) : 'Initial',
        description: 'First detected and registered at placement slot',
      },
      {
        stage: 'Latest Verification',
        timestamp: a.last_seen_at ? a.last_seen_at.replace('T', ' ').slice(0, 16) : 'Current',
        description: 'Confirmed active and visible on live publisher markup',
      },
    ],
  };
}

async function loadAds(websiteKey?: string): Promise<Advertisement[]> {
  if (websiteKey === 'et-brandequity' || websiteKey === 'et-brand-equity') websiteKey = 'et_brand_equity';
  const ads: Advertisement[] = [];
  let skip = 0;
  while (true) {
    const filter = websiteKey ? `&website=${encodeURIComponent(websiteKey)}` : '';
    const res = await apiFetch<ApiAdvertisementsResponse>(`/monitoring/advertisements?status=ACTIVE&identified_only=true&limit=200&skip=${skip}${filter}`);
    ads.push(...res.advertisements.map(mapApiAdToModel));
    skip += res.advertisements.length;
    if (!res.advertisements.length || skip >= res.total) return ads;
  }
}

export const advertisementService = {
  getAllAdvertisements: () => loadAds(),
  getAdvertisementsByWebsite: (websiteKey: string) => loadAds(websiteKey),
  async getAdvertisementById(id: string): Promise<Advertisement | null> {
    return mapApiAdToModel(await apiFetch<ApiAdvertisementItem>(`/monitoring/advertisements/${id}`));
  },
  getAdvertisementHistory: (id: string) => apiFetch(`/monitoring/advertisements/${id}/history`),
};
