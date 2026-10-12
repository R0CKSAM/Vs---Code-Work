import React, { useState, useEffect, useRef } from 'react';
import { Search, X, Newspaper, Megaphone, Globe, ArrowRight } from 'lucide-react';
import { mockNewsArticles } from '../../data/mock/news';
import { mockAdvertisements } from '../../data/mock/advertisements';
import { mockWebsites } from '../../data/mock/websites';

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectArticle: (id: string) => void;
  onSelectAd: (id: string) => void;
  onSelectWebsite: (id: string) => void;
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({
  isOpen,
  onClose,
  onSelectArticle,
  onSelectAd,
  onSelectWebsite,
}) => {
  const [query, setQuery] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 50);
    } else {
      setQuery('');
    }
  }, [isOpen]);

  // Handle Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const q = query.trim().toLowerCase();

  const matchingArticles = mockNewsArticles
    .filter(
      (a) =>
        !q ||
        a.headline.toLowerCase().includes(q) ||
        a.summary.toLowerCase().includes(q) ||
        a.section.toLowerCase().includes(q)
    )
    .slice(0, 3);

  const matchingAds = mockAdvertisements
    .filter(
      (ad) =>
        !q ||
        ad.advertiser.toLowerCase().includes(q) ||
        ad.brand.toLowerCase().includes(q) ||
        ad.campaign.toLowerCase().includes(q) ||
        ad.position.toLowerCase().includes(q)
    )
    .slice(0, 3);

  const matchingWebsites = mockWebsites
    .filter((w) => !q || w.name.toLowerCase().includes(q) || w.domain.toLowerCase().includes(q))
    .slice(0, 2);

  const hasResults =
    matchingArticles.length > 0 || matchingAds.length > 0 || matchingWebsites.length > 0;

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(15, 23, 42, 0.5)',
        backdropFilter: 'blur(3px)',
        zIndex: 200,
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'center',
        paddingTop: '80px',
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '640px',
          maxWidth: '92vw',
          backgroundColor: '#ffffff',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-dropdown)',
          border: '1px solid var(--border-light)',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          animation: 'fadeIn 0.15s ease-out',
        }}
      >
        {/* Search Input Box */}
        <div
          style={{
            padding: '16px 20px',
            borderBottom: '1px solid var(--border-light)',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
          }}
        >
          <Search size={18} color="var(--text-muted)" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search news, advertisers, brands, campaigns, websites..."
            style={{
              flex: 1,
              border: 'none',
              outline: 'none',
              fontSize: '15px',
              color: 'var(--text-main)',
              backgroundColor: 'transparent',
            }}
          />
          <button
            onClick={onClose}
            style={{
              padding: '4px',
              borderRadius: 'var(--radius-xs)',
              color: 'var(--text-muted)',
            }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Results List */}
        <div style={{ maxHeight: '420px', overflowY: 'auto', padding: '12px 14px' }}>
          {!hasResults ? (
            <div style={{ padding: '32px 16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
              No matches found for &ldquo;{query}&rdquo;
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {/* Websites */}
              {matchingWebsites.length > 0 && (
                <div>
                  <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-subtle)', textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: '6px', paddingLeft: '8px' }}>
                    Websites Monitored
                  </div>
                  {matchingWebsites.map((site) => (
                    <div
                      key={site.id}
                      onClick={() => {
                        onSelectWebsite(site.id);
                        onClose();
                      }}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '8px 10px',
                        borderRadius: 'var(--radius-sm)',
                        cursor: 'pointer',
                        fontSize: '13px',
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-surface-subtle)')}
                      onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <Globe size={15} color="var(--accent-primary)" />
                        <div>
                          <span style={{ fontWeight: 600 }}>{site.name}</span>
                          <span style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginLeft: '8px' }}>
                            {site.domain}
                          </span>
                        </div>
                      </div>
                      <ArrowRight size={13} color="var(--text-subtle)" />
                    </div>
                  ))}
                </div>
              )}

              {/* Articles */}
              {matchingArticles.length > 0 && (
                <div>
                  <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-subtle)', textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: '6px', paddingLeft: '8px' }}>
                    News Articles
                  </div>
                  {matchingArticles.map((art) => (
                    <div
                      key={art.id}
                      onClick={() => {
                        onSelectArticle(art.id);
                        onClose();
                      }}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '8px 10px',
                        borderRadius: 'var(--radius-sm)',
                        cursor: 'pointer',
                        fontSize: '13px',
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-surface-subtle)')}
                      onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', maxWidth: '85%' }}>
                        <Newspaper size={15} color="#0284c7" />
                        <div>
                          <div style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {art.headline}
                          </div>
                          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                            {art.source} • {art.section}
                          </span>
                        </div>
                      </div>
                      <ArrowRight size={13} color="var(--text-subtle)" />
                    </div>
                  ))}
                </div>
              )}

              {/* Advertisements */}
              {matchingAds.length > 0 && (
                <div>
                  <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-subtle)', textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: '6px', paddingLeft: '8px' }}>
                    Tracked Advertisements
                  </div>
                  {matchingAds.map((ad) => (
                    <div
                      key={ad.id}
                      onClick={() => {
                        onSelectAd(ad.id);
                        onClose();
                      }}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '8px 10px',
                        borderRadius: 'var(--radius-sm)',
                        cursor: 'pointer',
                        fontSize: '13px',
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-surface-subtle)')}
                      onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', maxWidth: '85%' }}>
                        <Megaphone size={15} color="#0d9488" />
                        <div>
                          <div style={{ fontWeight: 500 }}>
                            {ad.advertiser} — <span style={{ color: 'var(--text-muted)' }}>{ad.brand}</span>
                          </div>
                          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                            {ad.campaign} • {ad.website} ({ad.position.split('(')[0].trim()})
                          </span>
                        </div>
                      </div>
                      <ArrowRight size={13} color="var(--text-subtle)" />
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer shortcuts */}
        <div
          style={{
            padding: '10px 18px',
            borderTop: '1px solid var(--border-light)',
            backgroundColor: 'var(--bg-surface-subtle)',
            fontSize: '11.5px',
            color: 'var(--text-muted)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span>Use <strong>Esc</strong> to close</span>
          <span>Press <strong>Enter</strong> to select</span>
        </div>
      </div>
    </div>
  );
};
