import React, { useState, useEffect } from 'react';
import { WebsiteInfo, NewsArticle, Advertisement, ContentChange } from '../types/dashboard';
import { websiteService } from '../services/websiteService';
import { newsService } from '../services/newsService';
import { advertisementService } from '../services/advertisementService';
import { changeService } from '../services/changeService';
import { StatusBadge } from '../components/common/StatusBadge';
import { DataTable, Column } from '../components/common/DataTable';
import { NewsDetailDrawer } from '../components/news/NewsDetailDrawer';
import { AdvertisementDetailDrawer } from '../components/advertisements/AdvertisementDetailDrawer';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import {
  ArrowLeft,
  ExternalLink,
  RefreshCw,
  FileText,
  Megaphone,
  History,
  Info,
} from 'lucide-react';

interface WebsiteDetailPageProps {
  websiteId: string;
  onBack: () => void;
}

export const WebsiteDetailPage: React.FC<WebsiteDetailPageProps> = ({ websiteId, onBack }) => {
  const [error, setError] = useState<string | null>(null);
  const [site, setSite] = useState<WebsiteInfo | null>(null);
  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [ads, setAds] = useState<Advertisement[]>([]);
  const [changes, setChanges] = useState<ContentChange[]>([]);
  const [activeTab, setActiveTab] = useState<'overview' | 'news' | 'ads' | 'changes'>('overview');
  const [isLoading, setIsLoading] = useState(true);

  // Detail drawers
  const [selectedArticle, setSelectedArticle] = useState<NewsArticle | null>(null);
  const [selectedAd, setSelectedAd] = useState<Advertisement | null>(null);

  useEffect(() => {
    setIsLoading(true);
    Promise.all([
      websiteService.getWebsiteById(websiteId),
      newsService.getNewsBySource(websiteId),
      advertisementService.getAdvertisementsByWebsite(websiteId),
      changeService.getChangesByWebsite(websiteId),
    ]).then(([s, n, a, c]) => {
      setSite(s);
      setArticles(n);
      setAds(a);
      setChanges(c);
      setIsLoading(false);
    }).catch((err: Error) => { setError(err.message); setIsLoading(false); });
  }, [websiteId]);

  if (error) return <p role="alert">Unable to load live data: {error}</p>;

  if (isLoading || !site) {
    return (
      <div style={{ padding: '24px 0' }}>
        <LoadingSkeleton rows={5} height={80} />
      </div>
    );
  }

  const newsColumns: Column<NewsArticle>[] = [
    { key: 'published_time', header: 'Time', width: '110px' },
    {
      key: 'headline',
      header: 'Headline',
      render: (row) => (
        <div>
          <div style={{ fontWeight: 600, color: 'var(--text-main)' }}>{row.headline}</div>
          <div style={{ fontSize: '11.5px', color: 'var(--text-muted)' }}>{row.summary.slice(0, 90)}...</div>
        </div>
      ),
    },
    { key: 'section', header: 'Section', width: '140px' },
    {
      key: 'status',
      header: 'Status',
      width: '110px',
      render: (row) => <StatusBadge status={row.status} size="sm" />,
    },
  ];

  const adColumns: Column<Advertisement>[] = [
    { key: 'advertiser', header: 'Advertiser', width: '160px', sortable: true },
    { key: 'brand', header: 'Brand', width: '150px' },
    { key: 'campaign', header: 'Campaign' },
    { key: 'position', header: 'Position', width: '180px' },
    {
      key: 'status',
      header: 'Status',
      width: '100px',
      render: (row) => <StatusBadge status={row.status} size="sm" />,
    },
  ];

  const changeColumns: Column<ContentChange>[] = [
    { key: 'timestamp', header: 'Time', width: '130px' },
    {
      key: 'type',
      header: 'Type',
      width: '140px',
      render: (row) => <StatusBadge status={row.type} size="sm" />,
    },
    { key: 'item', header: 'Item' },
    { key: 'change_description', header: 'Description' },
  ];

  return (
    <div>
      {/* Back button */}
      <button
        onClick={onBack}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          fontSize: '12.5px',
          color: 'var(--text-muted)',
          marginBottom: '16px',
          padding: '4px 8px',
          borderRadius: 'var(--radius-xs)',
          backgroundColor: 'var(--bg-surface-subtle)',
          border: '1px solid var(--border-light)',
        }}
      >
        <ArrowLeft size={13} />
        <span>Back to All Websites</span>
      </button>

      {/* Header */}
      <div
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border-light)',
          borderRadius: 'var(--radius-md)',
          padding: '24px',
          marginBottom: '20px',
          boxShadow: 'var(--shadow-card)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '14px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <h1 style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-main)' }}>
                {site.name}
              </h1>
              <StatusBadge status={site.status} />
            </div>

            <a
              href={site.url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                fontSize: '13px',
                color: 'var(--accent-primary)',
                marginTop: '4px',
              }}
            >
              <span>{site.url}</span>
              <ExternalLink size={12} />
            </a>

            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '6px' }}>
              Category: <strong>{site.category}</strong> • Last polled: <strong>{site.last_checked}</strong>
            </div>
          </div>

          <button
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '8px 16px',
              backgroundColor: 'var(--accent-primary)',
              color: '#ffffff',
              borderRadius: 'var(--radius-sm)',
              fontSize: '13px',
              fontWeight: 500,
            }}
          >
            <RefreshCw size={13} />
            <span>Check Now</span>
          </button>
        </div>

        {/* KPI Row */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 1fr)',
            gap: '14px',
            marginTop: '20px',
            paddingTop: '20px',
            borderTop: '1px solid var(--border-subtle)',
          }}
        >
          <div style={{ backgroundColor: 'var(--bg-surface-subtle)', padding: '12px 14px', borderRadius: 'var(--radius-sm)' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Articles Today</span>
            <div style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-main)', marginTop: '2px' }}>
              {site.articles_detected}
            </div>
          </div>

          <div style={{ backgroundColor: 'var(--bg-surface-subtle)', padding: '12px 14px', borderRadius: 'var(--radius-sm)' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>New Articles</span>
            <div style={{ fontSize: '18px', fontWeight: 700, color: '#047857', marginTop: '2px' }}>
              {site.new_articles}
            </div>
          </div>

          <div style={{ backgroundColor: 'var(--bg-surface-subtle)', padding: '12px 14px', borderRadius: 'var(--radius-sm)' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Ads Tracked</span>
            <div style={{ fontSize: '18px', fontWeight: 700, color: '#0284c7', marginTop: '2px' }}>
              {site.advertisements_detected}
            </div>
          </div>

          <div style={{ backgroundColor: 'var(--bg-surface-subtle)', padding: '12px 14px', borderRadius: 'var(--radius-sm)' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Changes Today</span>
            <div style={{ fontSize: '18px', fontWeight: 700, color: '#b45309', marginTop: '2px' }}>
              {site.changes_today}
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div
        style={{
          display: 'flex',
          borderBottom: '1px solid var(--border-light)',
          marginBottom: '20px',
          gap: '8px',
        }}
      >
        <button
          onClick={() => setActiveTab('overview')}
          style={{
            padding: '10px 16px',
            fontSize: '13.5px',
            fontWeight: 500,
            color: activeTab === 'overview' ? 'var(--accent-primary)' : 'var(--text-muted)',
            borderBottom: activeTab === 'overview' ? '2px solid var(--accent-primary)' : '2px solid transparent',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <Info size={14} /> Overview
        </button>

        <button
          onClick={() => setActiveTab('news')}
          style={{
            padding: '10px 16px',
            fontSize: '13.5px',
            fontWeight: 500,
            color: activeTab === 'news' ? 'var(--accent-primary)' : 'var(--text-muted)',
            borderBottom: activeTab === 'news' ? '2px solid var(--accent-primary)' : '2px solid transparent',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <FileText size={14} /> News Articles ({articles.length})
        </button>

        <button
          onClick={() => setActiveTab('ads')}
          style={{
            padding: '10px 16px',
            fontSize: '13.5px',
            fontWeight: 500,
            color: activeTab === 'ads' ? 'var(--accent-primary)' : 'var(--text-muted)',
            borderBottom: activeTab === 'ads' ? '2px solid var(--accent-primary)' : '2px solid transparent',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <Megaphone size={14} /> Advertisements ({ads.length})
        </button>

        <button
          onClick={() => setActiveTab('changes')}
          style={{
            padding: '10px 16px',
            fontSize: '13.5px',
            fontWeight: 500,
            color: activeTab === 'changes' ? 'var(--accent-primary)' : 'var(--text-muted)',
            borderBottom: activeTab === 'changes' ? '2px solid var(--accent-primary)' : '2px solid transparent',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <History size={14} /> Changes ({changes.length})
        </button>
      </div>

      {/* Tab Contents */}
      {activeTab === 'overview' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '20px' }}>
          <div
            style={{
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-light)',
              borderRadius: 'var(--radius-md)',
              padding: '20px',
            }}
          >
            <h3 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '14px' }}>Crawl Configuration</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '13px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-muted)' }}>Target Hostname</span>
                <span style={{ fontFamily: 'var(--font-mono)' }}>{site.domain}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-muted)' }}>Polling Cadence</span>
                <span>Every 10 minutes</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-muted)' }}>Extraction Mode</span>
                <span>Scheduled Phase Scraper</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-muted)' }}>Average Latency</span>
                <span>{site.response_time_ms} ms</span>
              </div>
            </div>
          </div>

          <div
            style={{
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-light)',
              borderRadius: 'var(--radius-md)',
              padding: '20px',
            }}
          >
            <h3 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '14px' }}>Latest Activity Snapshot</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {changes.slice(0, 3).map((chg) => (
                <div
                  key={chg.id}
                  style={{
                    padding: '8px 10px',
                    backgroundColor: 'var(--bg-surface-subtle)',
                    borderRadius: 'var(--radius-xs)',
                    fontSize: '12px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ fontWeight: 600 }}>{chg.item}</span>
                    <span style={{ color: 'var(--text-muted)' }}>{chg.timestamp}</span>
                  </div>
                  <div style={{ color: 'var(--text-muted)', marginTop: '2px' }}>{chg.change_description}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'news' && (
        <DataTable
          columns={newsColumns}
          data={articles}
          keyExtractor={(a) => a.id}
          onRowClick={(a) => setSelectedArticle(a)}
        />
      )}

      {activeTab === 'ads' && (
        <DataTable
          columns={adColumns}
          data={ads}
          keyExtractor={(a) => a.id}
          onRowClick={(a) => setSelectedAd(a)}
        />
      )}

      {activeTab === 'changes' && (
        <DataTable
          columns={changeColumns}
          data={changes}
          keyExtractor={(c) => c.id}
        />
      )}

      {/* Drawers */}
      <NewsDetailDrawer
        article={selectedArticle}
        isOpen={Boolean(selectedArticle)}
        onClose={() => setSelectedArticle(null)}
      />

      <AdvertisementDetailDrawer
        ad={selectedAd}
        isOpen={Boolean(selectedAd)}
        onClose={() => setSelectedAd(null)}
      />
    </div>
  );
};
