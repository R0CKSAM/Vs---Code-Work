import { WebsiteInfo } from '../../types/dashboard';

export const mockWebsites: WebsiteInfo[] = [
  {
    id: 'et-brandequity',
    name: 'ET BrandEquity',
    url: 'https://brandequity.economictimes.indiatimes.com/',
    status: 'ONLINE',
    last_checked: '3 minutes ago',
    articles_detected: 28,
    new_articles: 8,
    advertisements_detected: 19,
    domain: 'brandequity.economictimes.indiatimes.com',
    category: 'Marketing & Brand Intelligence',
    response_time_ms: 320,
    changes_today: 14,
  },
  {
    id: 'exchange4media',
    name: 'Exchange4media',
    url: 'https://www.exchange4media.com/',
    status: 'ONLINE',
    last_checked: '5 minutes ago',
    articles_detected: 20,
    new_articles: 4,
    advertisements_detected: 15,
    domain: 'exchange4media.com',
    category: 'Media, Advertising & Broadcasting',
    response_time_ms: 410,
    changes_today: 9,
  },
];
