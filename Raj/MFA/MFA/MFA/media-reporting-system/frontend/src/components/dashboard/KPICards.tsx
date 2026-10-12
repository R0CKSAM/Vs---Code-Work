import React from 'react';
import {
  Globe,
  FileText,
  Sparkles,
  Megaphone,
  TrendingUp,
  Clock,
  Layers,
  FileEdit,
  CheckCircle,
} from 'lucide-react';
import { KPIData } from '../../types/dashboard';

interface KPICardsProps {
  kpis: KPIData;
}

export const KPICards: React.FC<KPICardsProps> = ({ kpis }) => {
  const primaryCards = [
    {
      label: 'Websites Monitored',
      value: kpis.websites_monitored.toString(),
      subtext: 'ET BrandEquity & Exchange4media',
      icon: <Globe size={18} />,
      trend: null,
    },
    {
      label: 'Articles Today',
      value: kpis.articles_today.toString(),
      subtext: `+${kpis.articles_change_pct}% vs yesterday`,
      icon: <FileText size={18} />,
      trend: true,
    },
    {
      label: 'New Articles',
      value: kpis.new_articles.toString(),
      subtext: kpis.new_articles_period || 'in last 2 hours',
      icon: <Sparkles size={18} />,
      trend: true,
    },
    {
      label: 'Advertisements Tracked',
      value: kpis.advertisements_tracked.toString(),
      subtext: `+${kpis.ads_change_pct}% this week`,
      icon: <Megaphone size={18} />,
      trend: true,
    },
  ];

  const intelligenceMetrics = [
    {
      label: 'Articles Last 24h',
      value: (kpis.articles_last_24h ?? 112).toString(),
      subtext: 'Across all sections',
      icon: <Clock size={16} />,
    },
    {
      label: 'New Advertisements',
      value: (kpis.new_advertisements_24h ?? 9).toString(),
      subtext: 'Fresh campaigns indexed',
      icon: <Layers size={16} />,
    },
    {
      label: 'Updated Content',
      value: (kpis.updated_content_24h ?? 16).toString(),
      subtext: 'Revisions & headline changes',
      icon: <FileEdit size={16} />,
    },
    {
      label: 'Pages Checked',
      value: (kpis.pages_checked_today ?? 144).toString(),
      subtext: 'Automated crawl cycles',
      icon: <CheckCircle size={16} />,
    },
  ];

  return (
    <div style={{ marginBottom: '28px' }}>
      {/* Primary KPI Row */}
      <div className="kpi-grid">
        {primaryCards.map((card, idx) => (
          <div key={idx} className="kpi-card">
            <div>
              <div className="kpi-card-header">
                <span className="kpi-label">{card.label}</span>
                <div className="kpi-icon-box">{card.icon}</div>
              </div>
              <div className="kpi-value">{card.value}</div>
            </div>
            <div className="kpi-subtext">
              {card.trend && <TrendingUp size={13} className="trend-positive" />}
              <span className={card.trend ? 'trend-positive' : ''}>{card.subtext}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Second Row Intelligence Metrics */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: '14px',
          marginTop: '-12px',
        }}
        className="intelligence-metrics-grid"
      >
        {intelligenceMetrics.map((item, idx) => (
          <div
            key={idx}
            style={{
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-light)',
              borderRadius: 'var(--radius-sm)',
              padding: '12px 16px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              boxShadow: 'var(--shadow-sm)',
            }}
          >
            <div>
              <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', fontWeight: 500 }}>
                {item.label}
              </div>
              <div style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-main)', marginTop: '2px' }}>
                {item.value}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-subtle)', marginTop: '1px' }}>
                {item.subtext}
              </div>
            </div>
            <div
              style={{
                width: '32px',
                height: '32px',
                borderRadius: 'var(--radius-xs)',
                backgroundColor: 'var(--bg-surface-subtle)',
                color: 'var(--text-muted)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              {item.icon}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
