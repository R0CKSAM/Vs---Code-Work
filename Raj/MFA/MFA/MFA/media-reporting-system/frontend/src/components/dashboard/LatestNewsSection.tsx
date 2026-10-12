import React from 'react';
import { Clock, BookOpen, ExternalLink, Newspaper } from 'lucide-react';
import { NewsArticle } from '../../types/dashboard';

interface LatestNewsSectionProps {
  articles: NewsArticle[];
  selectedWebsite?: string;
  selectedSection?: string;
  searchQuery?: string;
}

export const LatestNewsSection: React.FC<LatestNewsSectionProps> = ({
  articles,
  selectedWebsite = 'all',
  selectedSection = 'all',
  searchQuery = '',
}) => {
  // Client-side filtering preview
  const filteredArticles = articles.filter((item) => {
    const matchesWebsite =
      selectedWebsite === 'all' || item.source.toLowerCase().includes(selectedWebsite.toLowerCase());
    const matchesSection =
      selectedSection === 'all' || item.section.toLowerCase().includes(selectedSection.toLowerCase());
    const matchesSearch =
      !searchQuery ||
      item.headline.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.summary.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.source.toLowerCase().includes(searchQuery.toLowerCase());

    return matchesWebsite && matchesSection && matchesSearch;
  });

  return (
    <div>
      <div className="section-header">
        <div>
          <h2 className="section-title">Latest Media Intelligence & News</h2>
          <span className="section-subtitle">
            Showing {filteredArticles.length} recent articles detected across tracked industry publications
          </span>
        </div>
      </div>

      {filteredArticles.length === 0 ? (
        <div style={{
          textAlign: 'center',
          padding: '48px 24px',
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-light)',
          borderRadius: 'var(--radius-md)',
          color: 'var(--text-muted)'
        }}>
          <Newspaper size={36} style={{ margin: '0 auto 12px auto', color: 'var(--text-subtle)' }} />
          <p style={{ fontWeight: 500 }}>No articles match the current filter criteria.</p>
          <span style={{ fontSize: '12px' }}>Try resetting your search query or section filters.</span>
        </div>
      ) : (
        <div className="news-grid">
          {filteredArticles.map((article) => {
            const isET = article.source.includes('ET') || article.source.includes('BrandEquity');
            return (
              <div key={article.id} className="news-card">
                <div>
                  <div className="news-card-header">
                    <span className={`news-source-tag ${isET ? 'tag-et' : 'tag-e4m'}`}>
                      {article.source}
                    </span>
                    <span className="news-section-tag">{article.section}</span>
                  </div>

                  <h4 className="news-headline" title={article.headline}>
                    {article.headline}
                  </h4>

                  <p className="news-summary" title={article.summary}>
                    {article.summary}
                  </p>
                </div>

                <div className="news-footer">
                  <div className="news-meta-left">
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                      <Clock size={11} /> {article.published_time}
                    </span>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                      <BookOpen size={11} /> {article.read_time}
                    </span>
                  </div>

                  {article.url && (
                    <a
                      href={article.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="news-link-btn"
                      title="Open source publication"
                    >
                      <span>Read</span>
                      <ExternalLink size={10} />
                    </a>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
