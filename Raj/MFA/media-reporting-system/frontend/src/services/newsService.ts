import { NewsArticle } from '../types/dashboard';
import { apiFetch } from '../api/client';

interface ArticleResponse { articles: Array<{
  id: string; headline: string; summary?: string | null; website: string;
  website_key: string; section: string; published_at?: string | null;
  publication_label?: string | null; scraped_at: string; image_url?: string | null;
  url: string; content_hash: string;
}>; }

const sources = ['et-brand-equity', 'exchange4media'];
function publicationDisplay(value?: string | null, label?: string | null): string {
  if (!value) return label || 'Time pending verification';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('en-IN', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kolkata',
  }).format(date);
}
async function loadNews(): Promise<NewsArticle[]> {
  const responses = await Promise.all(sources.map(source =>
    apiFetch<ArticleResponse>(`/monitoring/${source}/articles`)));
  return responses.flatMap(response => response.articles.map(a => ({
    id: a.id, headline: a.headline, summary: a.summary || '', source: a.website,
    source_id: a.website_key === 'et_brand_equity' ? 'et-brandequity' : 'exchange4media',
    section: a.section, published_time: publicationDisplay(a.published_at, a.publication_label),
    first_seen: a.scraped_at, last_seen: a.scraped_at, status: 'UNCHANGED' as const,
    image_url: a.image_url, url: a.url, read_time: '', content_hash: a.content_hash,
  })));
}

export const newsService = {
  getAllNews: loadNews,
  async getNewsBySource(sourceId: string): Promise<NewsArticle[]> {
    return (await loadNews()).filter(a => a.source_id === sourceId);
  },
  async getArticleById(id: string): Promise<NewsArticle | null> {
    return (await loadNews()).find(a => a.id === id) || null;
  },
};
