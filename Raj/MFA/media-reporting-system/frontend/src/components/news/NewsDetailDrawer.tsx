import React from 'react';
import { NewsArticle } from '../../types/dashboard';
import { Drawer } from '../common/Drawer';
import { StatusBadge } from '../common/StatusBadge';
import { Clock, Eye, ExternalLink, Hash, History, User } from 'lucide-react';

interface NewsDetailDrawerProps {
  article: NewsArticle | null;
  isOpen: boolean;
  onClose: () => void;
}

export const NewsDetailDrawer: React.FC<NewsDetailDrawerProps> = ({
  article,
  isOpen,
  onClose,
}) => {
  if (!article) return null;

  const isET = article.source.includes('ET') || article.source.includes('BrandEquity');

  return (
    <Drawer
      isOpen={isOpen}
      onClose={onClose}
      title="Article Intelligence Detail"
      subtitle={`${article.source} • ${article.section}`}
      width="580px"
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {/* Status & Publication meta banner */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '12px 16px',
            backgroundColor: 'var(--bg-surface-subtle)',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border-light)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span
              style={{
                fontSize: '11px',
                fontWeight: 700,
                color: '#ffffff',
                backgroundColor: isET ? '#c2410c' : '#0369a1',
                padding: '3px 8px',
                borderRadius: 'var(--radius-xs)',
              }}
            >
              {article.source}
            </span>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Section: <strong>{article.section}</strong>
            </span>
          </div>

          <StatusBadge status={article.status} />
        </div>

        {/* Headline */}
        <div>
          <h3
            style={{
              fontSize: '18px',
              fontWeight: 700,
              color: 'var(--text-main)',
              lineHeight: 1.4,
              marginBottom: '10px',
            }}
          >
            {article.headline}
          </h3>

          {article.author && (
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '12.5px',
                color: 'var(--text-muted)',
              }}
            >
              <User size={13} />
              <span>By {article.author}</span>
            </div>
          )}
        </div>

        {/* Media Placeholder */}
        <div
          style={{
            height: '160px',
            backgroundColor: 'var(--bg-surface-subtle)',
            border: '1px dashed var(--border-light)',
            borderRadius: 'var(--radius-md)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-subtle)',
            gap: '6px',
          }}
        >
          <Eye size={24} />
          <span style={{ fontSize: '12px' }}>Editorial Visual Snapshot (Phase 2 Scraper Target)</span>
        </div>

        {/* Summary */}
        <div>
          <h4
            style={{
              fontSize: '12px',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.6px',
              color: 'var(--text-muted)',
              marginBottom: '8px',
            }}
          >
            Executive Summary
          </h4>
          <p
            style={{
              fontSize: '13.5px',
              color: 'var(--text-main)',
              lineHeight: 1.6,
              backgroundColor: '#ffffff',
              padding: '12px 14px',
              border: '1px solid var(--border-light)',
              borderRadius: 'var(--radius-sm)',
            }}
          >
            {article.summary}
          </p>
        </div>

        {/* Detection Metadata Grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(2, 1fr)',
            gap: '12px',
            backgroundColor: 'var(--bg-surface-subtle)',
            padding: '14px',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border-light)',
          }}
        >
          <div>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Published Time
            </span>
            <div style={{ fontSize: '12.5px', fontWeight: 600, color: 'var(--text-main)', marginTop: '2px', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Clock size={12} color="var(--text-muted)" /> {article.published_time}
            </div>
          </div>

          <div>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Read Time
            </span>
            <div style={{ fontSize: '12.5px', fontWeight: 600, color: 'var(--text-main)', marginTop: '2px' }}>
              {article.read_time}
            </div>
          </div>

          <div>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              First Seen by Crawler
            </span>
            <div style={{ fontSize: '12.5px', fontWeight: 600, color: 'var(--text-main)', marginTop: '2px' }}>
              {article.first_seen}
            </div>
          </div>

          <div>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Last Verified
            </span>
            <div style={{ fontSize: '12.5px', fontWeight: 600, color: 'var(--text-main)', marginTop: '2px' }}>
              {article.last_seen}
            </div>
          </div>
        </div>

        {/* Content Hash & Integrity */}
        <div>
          <h4
            style={{
              fontSize: '12px',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.6px',
              color: 'var(--text-muted)',
              marginBottom: '8px',
              display: 'flex',
              alignItems: 'center',
              gap: '5px',
            }}
          >
            <Hash size={13} /> Content Checksum
          </h4>
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '12px',
              backgroundColor: 'var(--bg-surface-subtle)',
              padding: '8px 12px',
              borderRadius: 'var(--radius-xs)',
              border: '1px solid var(--border-light)',
              color: 'var(--text-muted)',
              wordBreak: 'break-all',
            }}
          >
            {article.content_hash}
          </div>
        </div>

        {/* Change History Placeholder */}
        <div>
          <h4
            style={{
              fontSize: '12px',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.6px',
              color: 'var(--text-muted)',
              marginBottom: '8px',
              display: 'flex',
              alignItems: 'center',
              gap: '5px',
            }}
          >
            <History size={13} /> Editorial Revision History
          </h4>

          {article.change_history && article.change_history.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {article.change_history.map((chg, idx) => (
                <div
                  key={idx}
                  style={{
                    padding: '10px 12px',
                    border: '1px solid var(--border-light)',
                    borderRadius: 'var(--radius-xs)',
                    fontSize: '12px',
                    backgroundColor: '#ffffff',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <strong style={{ color: 'var(--text-main)' }}>Field changed: {chg.field}</strong>
                    <span style={{ color: 'var(--text-muted)' }}>{chg.timestamp}</span>
                  </div>
                  <div style={{ color: '#b91c1c', textDecoration: 'line-through' }}>{chg.old_value}</div>
                  <div style={{ color: '#047857', fontWeight: 500, marginTop: '2px' }}>{chg.new_value}</div>
                </div>
              ))}
            </div>
          ) : (
            <div
              style={{
                padding: '12px',
                fontSize: '12.5px',
                color: 'var(--text-muted)',
                backgroundColor: 'var(--bg-surface-subtle)',
                borderRadius: 'var(--radius-xs)',
                border: '1px solid var(--border-light)',
              }}
            >
              No editorial modifications detected since initial crawl.
            </div>
          )}
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: '10px', paddingTop: '10px' }}>
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              flex: 1,
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
              padding: '9px 16px',
              backgroundColor: 'var(--accent-primary)',
              color: '#ffffff',
              borderRadius: 'var(--radius-sm)',
              fontSize: '13px',
              fontWeight: 500,
            }}
          >
            <span>Open Source Publication</span>
            <ExternalLink size={13} />
          </a>

          <button
            onClick={onClose}
            style={{
              padding: '9px 18px',
              backgroundColor: 'var(--bg-surface-subtle)',
              border: '1px solid var(--border-light)',
              color: 'var(--text-main)',
              borderRadius: 'var(--radius-sm)',
              fontSize: '13px',
              fontWeight: 500,
            }}
          >
            Close
          </button>
        </div>
      </div>
    </Drawer>
  );
};
