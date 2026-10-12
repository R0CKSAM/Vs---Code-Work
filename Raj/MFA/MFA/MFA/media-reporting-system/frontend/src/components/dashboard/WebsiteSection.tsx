import React from 'react';
import { ExternalLink, Radio, CheckCircle2 } from 'lucide-react';
import { WebsiteInfo } from '../../types/dashboard';
import { Badge } from '../common/Badge';

interface WebsiteSectionProps {
  websites: WebsiteInfo[];
  onSelectWebsite?: (id: string) => void;
}

export const WebsiteSection: React.FC<WebsiteSectionProps> = ({ websites, onSelectWebsite }) => {
  return (
    <div style={{ marginBottom: '32px' }}>
      <div className="section-header">
        <div>
          <h2 className="section-title">Website Monitoring</h2>
          <span className="section-subtitle">Active sources targeted for automated monitoring</span>
        </div>
        <Badge variant="neutral" icon={<Radio size={12} color="#0284c7" />}>
          2 Target Feeds Configured
        </Badge>
      </div>

      <div className="website-grid">
        {websites.map((site) => {
          const isET = site.id.includes('et') || site.name.includes('ET');
          return (
            <div
              key={site.id}
              className="website-card"
              onClick={() => onSelectWebsite && onSelectWebsite(site.id)}
              style={{ cursor: onSelectWebsite ? 'pointer' : 'default' }}
            >
              <div className="website-card-top">
                <div className="website-info-box">
                  <div className={`site-logo-badge ${isET ? 'logo-et' : 'logo-e4m'}`}>
                    {isET ? 'ET' : 'E4M'}
                  </div>
                  <div className="website-name-wrap">
                    <h3>{site.name}</h3>
                    <a
                      href={site.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="website-url"
                    >
                      <span>{site.domain}</span>
                      <ExternalLink size={11} />
                    </a>
                  </div>
                </div>

                <Badge variant="success" icon={<CheckCircle2 size={12} />}>
                  {site.status}
                </Badge>
              </div>

              <div className="website-stats-row">
                <div className="stat-item">
                  <span className="stat-label">Category</span>
                  <span className="stat-value">{site.category.split('&')[0].trim()}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Last Checked</span>
                  <span className="stat-value">{site.last_checked}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Articles Detected</span>
                  <span className="stat-value">{site.articles_detected} today</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
