import { DashboardResponse } from '../types/dashboard';

export const fallbackDashboardData: DashboardResponse = {
  system_status: {
    status: "Monitoring Active",
    subtitle: "Media monitoring and intelligence dashboard",
    current_date: "Wednesday, September 23, 2026",
    last_updated: "Today at 12:15 IST",
    environment: "Client Mock Fallback (Phase 0)"
  },
  kpis: {
    websites_monitored: 2,
    articles_today: 48,
    new_articles: 12,
    advertisements_tracked: 34,
    articles_change_pct: 14.5,
    new_articles_period: "in last 2 hours",
    ads_change_pct: 8.2
  },
  websites: [
    {
      id: "et-brandequity",
      name: "ET BrandEquity",
      url: "https://brandequity.economictimes.indiatimes.com/",
      status: "Monitoring",
      last_checked: "4 minutes ago",
      articles_detected: 28,
      domain: "brandequity.economictimes.indiatimes.com",
      category: "Marketing & Brand Intelligence"
    },
    {
      id: "exchange4media",
      name: "Exchange4media",
      url: "https://www.exchange4media.com/",
      status: "Monitoring",
      last_checked: "7 minutes ago",
      articles_detected: 20,
      domain: "exchange4media.com",
      category: "Media, Advertising & Broadcasting"
    }
  ],
  latest_news: [
    {
      id: "news-001",
      headline: "FMCG Conglomerates Reallocate Festive Ad Spends Toward Regional Connected TV Platforms",
      summary: "Leading consumer goods enterprises are shifting up to 35% of their festival broadcast budgets toward regional language CTV platforms, prioritizing micro-targeting over linear TV prime slots.",
      source: "ET BrandEquity",
      section: "Digital Advertising",
      published_time: "28 mins ago",
      read_time: "3 min read",
      url: "https://brandequity.economictimes.indiatimes.com/"
    },
    {
      id: "news-002",
      headline: "Unified Cross-Screen Measurement Standard Proposed by Premier Broadcasters and Tech Alliance",
      summary: "Industry bodies and digital video publishers have initiated consultations to establish a standardized single-source cross-screen audience measurement framework to unify linear and OTT metrics.",
      source: "Exchange4media",
      section: "Broadcasting",
      published_time: "42 mins ago",
      read_time: "4 min read",
      url: "https://www.exchange4media.com/"
    },
    {
      id: "news-003",
      headline: "Automotive Brands Ramp Up Experiential and Dynamic Creative Campaigns Ahead of EV Launches",
      summary: "Automotive OEMs are deploying programmatic dynamic creative optimization (DCO) alongside hyper-local retail showroom activations to drive pre-bookings for emerging electric passenger vehicles.",
      source: "ET BrandEquity",
      section: "Marketing",
      published_time: "1 hour ago",
      read_time: "2 min read",
      url: "https://brandequity.economictimes.indiatimes.com/"
    },
    {
      id: "news-004",
      headline: "Ad-Tech Consortia Roll Out Privacy-Preserving Alternative Identifier Frameworks for Retail Media",
      summary: "With privacy guidelines tightening, retail media networks are piloting first-party data clean rooms and identity graph syndication to provide closed-loop attribution without third-party cookies.",
      source: "Exchange4media",
      section: "Ad Tech",
      published_time: "2 hours ago",
      read_time: "5 min read",
      url: "https://www.exchange4media.com/"
    },
    {
      id: "news-005",
      headline: "Quick-Commerce Platforms Expand In-App Sponsored Display and Search Real Estate",
      summary: "Ultra-fast grocery delivery operators are projecting retail media advertising to contribute up to 18% of aggregate platform revenue by end of current fiscal cycle through sponsored carousels.",
      source: "ET BrandEquity",
      section: "Retail Media",
      published_time: "3 hours ago",
      read_time: "3 min read",
      url: "https://brandequity.economictimes.indiatimes.com/"
    },
    {
      id: "news-006",
      headline: "Independent Agency Networks Capture Major Share of High-Growth D2C Brand Account Moves",
      summary: "Mid-tier creative boutiques and performance marketing independent agencies secured over 60% of reviewed digital brand mandates in the past quarter, outpacing traditional holding company rosters.",
      source: "Exchange4media",
      section: "Agencies",
      published_time: "4 hours ago",
      read_time: "4 min read",
      url: "https://www.exchange4media.com/"
    }
  ],
  advertisements_summary: [
    {
      id: "ad-001",
      brand_name: "Nexus Smartphone Ultra",
      format: "Masthead Banner (970x250)",
      placement: "Homepage Hero Billboard",
      first_seen: "Today 08:30 AM",
      status: "Active"
    },
    {
      id: "ad-002",
      brand_name: "Aura FinTech Platinum",
      format: "In-article Sponsored Story",
      placement: "Business & Financial News Section",
      first_seen: "Today 09:15 AM",
      status: "Active"
    },
    {
      id: "ad-003",
      brand_name: "Zenith Electric SUV",
      format: "Sticky Footer Video Overlay",
      placement: "Auto Category Pages",
      first_seen: "Today 10:00 AM",
      status: "Active"
    }
  ]
};
