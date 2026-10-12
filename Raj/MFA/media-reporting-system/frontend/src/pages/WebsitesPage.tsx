import React, { useState, useEffect } from 'react';
import { WebsiteInfo } from '../types/dashboard';
import { websiteService } from '../services/websiteService';
import { StatusBadge } from '../components/common/StatusBadge';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import { Globe, ExternalLink, RefreshCw, ArrowRight, Radio } from 'lucide-react';

interface WebsitesPageProps {
  onSelectWebsiteDetail: (websiteId: string) => void;
}

export const WebsitesPage: React.FC<WebsitesPageProps> = ({ onSelectWebsiteDetail }) => {
  const [websites, setWebsites] = useState<WebsiteInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [checkingId, setCheckingId] = useState<string | null>(null);
  const [alertMsg, setAlertMsg] = useState<string | null>(null);

  useEffect(() => {
    websiteService.getAllWebsites().then((res) => {
      setWebsites(res);
      setIsLoading(false);
    }).catch((err: Error) => { setAlertMsg(err.message); setIsLoading(false); });
  }, []);

  const handleCheckNow = async (id: string, name: string) => {
    setCheckingId(id);
    try {
      const res = await websiteService.triggerCheck(id);
      setAlertMsg(res.message);
    } catch (err) {
      setAlertMsg(err instanceof Error ? err.message : 'Live check failed');
    } finally {
      setCheckingId(null);
    }
    setTimeout(() => setAlertMsg(null), 4000);
  };

  if (isLoading) {
    return (
      <div style={{ padding: '20px 0' }}>
        <LoadingSkeleton rows={4} height={120} />
      </div>
    );
  }

  return (
    <div>
      {/* Top Banner Alert */}
      {alertMsg && (
        <div
          style={{
            padding: '10px 16px',
            backgroundColor: '#ecfdf5',
            border: '1px solid #a7f3d0',
            borderRadius: 'var(--radius-sm)',
            color: '#065f46',
            fontSize: '13px',
            marginBottom: '18px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span>{alertMsg}</span>
          <button onClick={() => setAlertMsg(null)} style={{ fontSize: '11px', color: '#047857' }}>
            Dismiss
          </button>
        </div>
      )}

      {/* Header */}
      <div className="section-header" style={{ marginBottom: '20px' }}>
        <div>
          <h1 style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-main)' }}>
            Website Monitoring
          </h1>
          <p style={{ fontSize: '13.5px', color: 'var(--text-muted)' }}>
            Configured media publications under automated intelligence tracking
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span
            style={{
              fontSize: '12px',
              fontFamily: 'var(--font-mono)',
              padding: '4px 8px',
              backgroundColor: 'var(--bg-surface-subtle)',
              border: '1px solid var(--border-light)',
              borderRadius: 'var(--radius-xs)',
              color: 'var(--text-muted)',
            }}
          >
            Interval: 10 min
          </span>
        </div>
      </div>

      {/* Websites Grid */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
        {websites.map((site) => {
          const isET = site.id.includes('et') || site.name.includes('ET');
          const isChecking = checkingId === site.id;

          return (
            <div
              key={site.id}
              style={{
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border-light)',
                borderRadius: 'var(--radius-md)',
                padding: '24px',
                boxShadow: 'var(--shadow-card)',
                display: 'flex',
                flexDirection: 'column',
                gap: '18px',
              }}
            >
              {/* Card Top */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '14px' }}>
                <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
                  <div
                    style={{
                      width: '48px',
                      height: '48px',
                      borderRadius: 'var(--radius-sm)',
                      backgroundColor: isET ? '#c2410c' : '#0369a1',
                      color: '#ffffff',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontWeight: 700,
                      fontSize: '18px',
                    }}
                  >
                    {isET ? 'ET' : 'E4M'}
                  </div>
                  <div>
                    <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-main)' }}>
                      {site.name}
                    </h3>
                    <a
                      href={site.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                        fontSize: '12.5px',
                        color: 'var(--text-muted)',
                        marginTop: '2px',
                      }}
                    >
                      <span>{site.domain}</span>
                      <ExternalLink size={12} />
                    </a>
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <StatusBadge status={site.status} />

                  <button
                    onClick={() => handleCheckNow(site.id, site.name)}
                    disabled={isChecking}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '5px',
                      padding: '6px 12px',
                      backgroundColor: 'var(--bg-surface-subtle)',
                      border: '1px solid var(--border-light)',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: '12px',
                      fontWeight: 500,
                      color: 'var(--text-main)',
                      cursor: isChecking ? 'not-allowed' : 'pointer',
                    }}
                    title="Simulate immediate crawler poll"
                  >
                    <RefreshCw
                      size={12}
                      style={{ animation: isChecking ? 'spin 1s linear infinite' : 'none' }}
                    />
                    <span>{isChecking ? 'Checking...' : 'Check Now'}</span>
                  </button>

                  <button
                    onClick={() => onSelectWebsiteDetail(site.id)}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '5px',
                      padding: '6px 14px',
                      backgroundColor: 'var(--accent-primary)',
                      color: '#ffffff',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: '12px',
                      fontWeight: 500,
                    }}
                  >
                    <span>View Details</span>
                    <ArrowRight size={13} />
                  </button>
                </div>
              </div>

              {/* Stats Bar */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(5, 1fr)',
                  backgroundColor: 'var(--bg-surface-subtle)',
                  border: '1px solid var(--border-light)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '14px 18px',
                  gap: '12px',
                }}
              >
                <div>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                    Category
                  </span>
                  <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginTop: '2px' }}>
                    {site.category.split('&')[0].trim()}
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                    Last Checked
                  </span>
                  <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginTop: '2px' }}>
                    {site.last_checked}
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                    Articles Today
                  </span>
                  <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginTop: '2px' }}>
                    {site.articles_detected} ({site.new_articles} new)
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                    Ads Tracked
                  </span>
                  <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginTop: '2px' }}>
                    {site.advertisements_detected} active
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                    Response Latency
                  </span>
                  <div style={{ fontSize: '13px', fontWeight: 600, color: '#047857', marginTop: '2px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Radio size={12} /> {site.response_time_ms} ms
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
