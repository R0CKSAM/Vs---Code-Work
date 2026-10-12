import React, { useEffect, useState } from 'react';
import { Advertisement } from '../../types/dashboard';
import { advertisementService } from '../../services/advertisementService';
import { Drawer } from '../common/Drawer';
import { StatusBadge } from '../common/StatusBadge';
import { Megaphone, Image as ImageIcon, ExternalLink, Hash, Clock, Layers, Globe, ShieldCheck } from 'lucide-react';

interface AdvertisementDetailDrawerProps {
  ad: Advertisement | null;
  isOpen: boolean;
  onClose: () => void;
}

export const AdvertisementDetailDrawer: React.FC<AdvertisementDetailDrawerProps> = ({
  ad,
  isOpen,
  onClose,
}) => {
  const [historyData, setHistoryData] = useState<any>(null);
  const [imgError, setImgError] = useState(false);

  useEffect(() => {
    if (ad && isOpen) {
      setImgError(false);
      advertisementService.getAdvertisementHistory(ad.id).then((res) => {
        setHistoryData(res);
      }).catch(() => setHistoryData(null));
    } else {
      setHistoryData(null);
    }
  }, [ad, isOpen]);

  if (!ad) return null;

  const advertiserDisplay = ad.advertiser || ad.brand || 'Identity unavailable from source';
  const brandDisplay = ad.brand || ad.advertiser || 'Identity unavailable from source';
  const campaignDisplay = ad.campaign || 'Campaign name not supplied';

  return (
    <Drawer
      isOpen={isOpen}
      onClose={onClose}
      title="Advertisement Evidence & Intelligence"
      subtitle={`${ad.website} • Placement ID: ${ad.id}`}
      width="600px"
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {/* Top Status & Header Card */}
        <div
          style={{
            padding: '14px 18px',
            backgroundColor: 'var(--bg-surface-subtle)',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border-light)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.6px' }}>
              Detected Placement
            </div>
            <div style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-main)', marginTop: '2px' }}>
              {ad.position}
            </div>
          </div>
          <StatusBadge status={ad.status} />
        </div>

        {/* Primary Identification Grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(2, 1fr)',
            gap: '12px',
            backgroundColor: '#ffffff',
            border: '1px solid var(--border-light)',
            borderRadius: 'var(--radius-sm)',
            padding: '14px',
          }}
        >
          <div>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Advertiser</span>
            <div style={{ fontSize: '13px', fontWeight: 600, color: ad.advertiser ? 'var(--text-main)' : 'var(--text-subtle)', marginTop: '2px' }}>
              {advertiserDisplay}
            </div>
          </div>

          <div>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Brand</span>
            <div style={{ fontSize: '13px', fontWeight: 600, color: ad.brand ? 'var(--text-main)' : 'var(--text-subtle)', marginTop: '2px' }}>
              {brandDisplay}
            </div>
          </div>

          <div>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Publisher</span>
            <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginTop: '2px' }}>
              {ad.website}
            </div>
          </div>

          <div>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Section</span>
            <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginTop: '2px' }}>
              {ad.section_page || 'Overall'}
            </div>
          </div>

          <div>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Ad Format / Type</span>
            <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginTop: '2px' }}>
              {ad.ad_type || ad.format || 'BANNER'}
            </div>
          </div>

          <div>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Campaign</span>
            <div style={{ fontSize: '13px', fontWeight: 600, color: ad.campaign ? 'var(--text-main)' : 'var(--text-subtle)', marginTop: '2px' }}>
              {campaignDisplay}
            </div>
          </div>
        </div>

        {/* Timing Intelligence */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(2, 1fr)',
            gap: '12px',
            backgroundColor: 'var(--bg-surface-subtle)',
            border: '1px solid var(--border-light)',
            borderRadius: 'var(--radius-sm)',
            padding: '12px 14px',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              <Clock size={12} /> First Seen
            </div>
            <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginTop: '2px' }}>
              {ad.first_seen_at || ad.first_seen || 'Not available'}
            </div>
          </div>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              <Clock size={12} /> Last Seen
            </div>
            <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', marginTop: '2px' }}>
              {ad.last_seen_at || ad.last_seen || 'Not available'}
            </div>
          </div>
        </div>

        {/* Captured Visual Creative Evidence */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <h4 style={{ fontSize: '12px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.6px', color: 'var(--text-muted)' }}>
              Captured Creative Asset
            </h4>
            <span style={{ fontSize: '11px', color: 'var(--text-subtle)' }}>Verified Local Evidence</span>
          </div>

          <div
            style={{
              minHeight: '180px',
              backgroundColor: 'var(--bg-surface-subtle)',
              border: '1px solid var(--border-light)',
              borderRadius: 'var(--radius-md)',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '16px',
              textAlign: 'center',
            }}
          >
            {ad.screenshot_url && !imgError ? (
              <img
                src={ad.screenshot_url}
                alt="Captured Ad Creative"
                onError={() => setImgError(true)}
                style={{
                  maxWidth: '100%',
                  maxHeight: '220px',
                  objectFit: 'contain',
                  borderRadius: 'var(--radius-xs)',
                  boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
                }}
              />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px', color: 'var(--text-subtle)' }}>
                <ImageIcon size={32} />
                <span style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-muted)' }}>
                  {ad.ad_type === 'IFRAME' ? 'Dynamic Iframe Ad Unit' : 'Creative asset image capture in progress'}
                </span>
                <span style={{ fontSize: '11px', color: 'var(--text-subtle)', maxWidth: '400px' }}>
                  {ad.local_image_path
                    ? `Archived at ${ad.local_image_path}`
                    : 'Target creative URL recorded in evidence registry'}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Technical Registry Evidence */}
        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--border-light)',
            borderRadius: 'var(--radius-sm)',
            padding: '12px 14px',
            display: 'flex',
            flexDirection: 'column',
            gap: '8px',
            fontSize: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '6px' }}>
            <Globe size={13} style={{ marginTop: '2px', color: 'var(--text-muted)', flexShrink: 0 }} />
            <div style={{ wordBreak: 'break-all' }}>
              <span style={{ color: 'var(--text-muted)' }}>Page URL: </span>
              {ad.page_url ? (
                <a href={ad.page_url} target="_blank" rel="noreferrer" style={{ color: 'var(--accent-primary)' }}>
                  {ad.page_url} <ExternalLink size={10} style={{ display: 'inline' }} />
                </a>
              ) : (
                <span style={{ color: 'var(--text-subtle)' }}>Not available</span>
              )}
            </div>
          </div>

          {ad.image_url && (
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '6px' }}>
              <ImageIcon size={13} style={{ marginTop: '2px', color: 'var(--text-muted)', flexShrink: 0 }} />
              <div style={{ wordBreak: 'break-all' }}>
                <span style={{ color: 'var(--text-muted)' }}>Creative Source URL: </span>
                <a href={ad.image_url} target="_blank" rel="noreferrer" style={{ color: 'var(--accent-primary)' }}>
                  {ad.image_url} <ExternalLink size={10} style={{ display: 'inline' }} />
                </a>
              </div>
            </div>
          )}

          {ad.ad_hash && (
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '6px' }}>
              <Hash size={13} style={{ marginTop: '2px', color: 'var(--text-muted)', flexShrink: 0 }} />
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)', wordBreak: 'break-all' }}>
                SHA-256 Hash: {ad.ad_hash}
              </div>
            </div>
          )}
        </div>

        {/* Version History if Multiple Versions Exist */}
        {historyData && historyData.versions && historyData.versions.length > 1 && (
          <div>
            <h4 style={{ fontSize: '12px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.6px', color: 'var(--text-muted)', marginBottom: '8px' }}>
              Creative Revision History ({historyData.versions.length} Versions)
            </h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {historyData.versions.map((v: any) => (
                <div
                  key={v.id}
                  style={{
                    padding: '10px 12px',
                    border: '1px solid var(--border-light)',
                    borderRadius: 'var(--radius-xs)',
                    backgroundColor: 'var(--bg-surface-subtle)',
                    fontSize: '12px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 600 }}>
                    <span>Version {v.version_number} ({v.change_type})</span>
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{v.detected_at}</span>
                  </div>
                  <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '2px' }}>
                    Advertiser: {v.advertiser || 'None'} • Brand: {v.brand || 'None'}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Close Button */}
        <div>
          <button
            onClick={onClose}
            style={{
              width: '100%',
              padding: '9px 16px',
              backgroundColor: 'var(--accent-primary)',
              color: '#ffffff',
              borderRadius: 'var(--radius-sm)',
              fontSize: '13px',
              fontWeight: 500,
              cursor: 'pointer',
              border: 'none',
            }}
          >
            Close Evidence Panel
          </button>
        </div>
      </div>
    </Drawer>
  );
};
