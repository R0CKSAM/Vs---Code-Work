import React, { useState, useEffect, useMemo } from 'react';
import { NewsArticle } from '../types/dashboard';
import { newsService } from '../services/newsService';
import { DataTable, Column } from '../components/common/DataTable';
import { StatusBadge } from '../components/common/StatusBadge';
import { NewsDetailDrawer } from '../components/news/NewsDetailDrawer';
import { Search, SlidersHorizontal, Eye, ExternalLink, RotateCcw } from 'lucide-react';

interface NewsPageProps {
  initialArticleId?: string | null;
}

export const NewsPage: React.FC<NewsPageProps> = ({ initialArticleId }) => {
  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState('');
  const [websiteFilter, setWebsiteFilter] = useState('all');
  const [sectionFilter, setSectionFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');

  // Selected article for drawer
  const [selectedArticle, setSelectedArticle] = useState<NewsArticle | null>(null);

  useEffect(() => {
    newsService.getAllNews().then((data) => {
      setArticles(data);
      setIsLoading(false);

      if (initialArticleId) {
        const found = data.find((a) => a.id === initialArticleId);
        if (found) setSelectedArticle(found);
      }
    }).catch((err: Error) => { setError(err.message); setIsLoading(false); });
  }, [initialArticleId]);

  const filteredArticles = useMemo(() => {
    return articles.filter((art) => {
      const matchSearch =
        !search ||
        art.headline.toLowerCase().includes(search.toLowerCase()) ||
        art.summary.toLowerCase().includes(search.toLowerCase()) ||
        (art.author && art.author.toLowerCase().includes(search.toLowerCase()));

      const matchWebsite =
        websiteFilter === 'all' || art.source.toLowerCase().includes(websiteFilter.toLowerCase());

      const matchSection =
        sectionFilter === 'all' || art.section.toLowerCase().includes(sectionFilter.toLowerCase());

      const matchStatus = statusFilter === 'all' || art.status === statusFilter;

      return matchSearch && matchWebsite && matchSection && matchStatus;
    });
  }, [articles, search, websiteFilter, sectionFilter, statusFilter]);

  const handleResetFilters = () => {
    setSearch('');
    setWebsiteFilter('all');
    setSectionFilter('all');
    setStatusFilter('all');
  };

  const columns: Column<NewsArticle>[] = [
    {
      key: 'published_time',
      header: 'Time',
      width: '105px',
      sortable: true,
      render: (row) => <span style={{ color: 'var(--text-muted)' }}>{row.published_time}</span>,
    },
    {
      key: 'headline',
      header: 'Headline & Summary',
      sortable: true,
      render: (row) => (
        <div style={{ maxWidth: '480px' }}>
          <div
            style={{
              fontWeight: 600,
              color: 'var(--text-main)',
              lineHeight: 1.35,
              fontSize: '13.5px',
            }}
          >
            {row.headline}
          </div>
          <div
            style={{
              fontSize: '12px',
              color: 'var(--text-muted)',
              marginTop: '4px',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {row.summary}
          </div>
        </div>
      ),
    },
    {
      key: 'source',
      header: 'Source',
      width: '140px',
      sortable: true,
      render: (row) => {
        const isET = row.source.includes('ET') || row.source.includes('BrandEquity');
        return (
          <span
            style={{
              fontSize: '11.5px',
              fontWeight: 600,
              padding: '2px 7px',
              borderRadius: '3px',
              backgroundColor: isET ? '#fef2f2' : '#f0f9ff',
              color: isET ? '#b91c1c' : '#0369a1',
              border: `1px solid ${isET ? '#fecaca' : '#bae6fd'}`,
            }}
          >
            {row.source}
          </span>
        );
      },
    },
    {
      key: 'section',
      header: 'Section',
      width: '140px',
      sortable: true,
      render: (row) => (
        <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{row.section}</span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      width: '110px',
      sortable: true,
      render: (row) => <StatusBadge status={row.status} size="sm" />,
    },
    {
      key: 'first_seen',
      header: 'First Seen',
      width: '120px',
      render: (row) => (
        <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{row.first_seen}</span>
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      width: '90px',
      align: 'right',
      render: (row) => (
        <div style={{ display: 'inline-flex', gap: '6px' }} onClick={(e) => e.stopPropagation()}>
          <button
            onClick={() => setSelectedArticle(row)}
            style={{
              padding: '4px 8px',
              backgroundColor: 'var(--bg-surface-subtle)',
              border: '1px solid var(--border-light)',
              borderRadius: 'var(--radius-xs)',
              fontSize: '11.5px',
              color: 'var(--text-main)',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '3px',
            }}
            title="Inspect in detail drawer"
          >
            <Eye size={12} />
            <span>View</span>
          </button>
        </div>
      ),
    },
  ];

  return (
    <div>
      {error && <p role="alert">Unable to load live data: {error}</p>}
      {/* Page Header */}
      <div className="section-header" style={{ marginBottom: '18px' }}>
        <div>
          <h1 style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-main)' }}>
            News Intelligence Monitoring
          </h1>
          <p style={{ fontSize: '13.5px', color: 'var(--text-muted)' }}>
            Real-time feed of detected articles, headlines, editorial changes, and content integrity hashes
          </p>
        </div>
        <span
          style={{
            fontSize: '12px',
            padding: '4px 10px',
            backgroundColor: 'var(--bg-surface-subtle)',
            border: '1px solid var(--border-light)',
            borderRadius: 'var(--radius-xs)',
            color: 'var(--text-muted)',
          }}
        >
          {filteredArticles.length} Articles Tracked
        </span>
      </div>

      {/* Filter and Search Bar */}
      <div
        style={{
          backgroundColor: '#ffffff',
          border: '1px solid var(--border-light)',
          borderRadius: 'var(--radius-md)',
          padding: '14px 18px',
          marginBottom: '20px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '12px',
          boxShadow: 'var(--shadow-sm)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap', flex: 1 }}>
          {/* Local Search Input */}
          <div style={{ position: 'relative', width: '280px' }}>
            <Search
              size={14}
              style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }}
            />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search headline, summary, author..."
              style={{
                width: '100%',
                height: '34px',
                paddingLeft: '32px',
                paddingRight: '12px',
                fontSize: '12.5px',
                backgroundColor: 'var(--bg-surface-subtle)',
                border: '1px solid var(--border-light)',
                borderRadius: 'var(--radius-sm)',
                outline: 'none',
              }}
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--text-muted)' }}>
            <SlidersHorizontal size={13} /> Filters:
          </div>

          {/* Website Filter */}
          <select
            value={websiteFilter}
            onChange={(e) => setWebsiteFilter(e.target.value)}
            className="filter-select"
          >
            <option value="all">All Sources</option>
            <option value="ET BrandEquity">ET BrandEquity</option>
            <option value="Exchange4media">Exchange4media</option>
          </select>

          {/* Section Filter */}
          <select
            value={sectionFilter}
            onChange={(e) => setSectionFilter(e.target.value)}
            className="filter-select"
          >
            <option value="all">All Sections</option>
            <option value="Digital Advertising">Digital Advertising</option>
            <option value="Broadcasting">Broadcasting</option>
            <option value="Marketing">Marketing</option>
            <option value="Ad Tech">Ad Tech</option>
            <option value="Retail Media">Retail Media</option>
            <option value="Agencies">Agencies</option>
          </select>

          {/* Status Filter */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="filter-select"
          >
            <option value="all">All Statuses</option>
            <option value="NEW">NEW</option>
            <option value="UPDATED">UPDATED</option>
            <option value="UNCHANGED">UNCHANGED</option>
          </select>
        </div>

        <button
          onClick={handleResetFilters}
          style={{
            fontSize: '12px',
            color: 'var(--text-muted)',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
            padding: '6px 10px',
            borderRadius: 'var(--radius-xs)',
          }}
        >
          <RotateCcw size={11} /> Reset
        </button>
      </div>

      {/* News Data Table */}
      <DataTable
        columns={columns}
        data={filteredArticles}
        keyExtractor={(a) => a.id}
        onRowClick={(a) => setSelectedArticle(a)}
        isLoading={isLoading}
        emptyTitle="No articles matched your filters"
        emptyDescription="Try clearing search keywords or selecting different sections."
        pageSize={8}
        highlightedId={selectedArticle?.id}
      />

      {/* Article Detail Drawer */}
      <NewsDetailDrawer
        article={selectedArticle}
        isOpen={Boolean(selectedArticle)}
        onClose={() => setSelectedArticle(null)}
      />
    </div>
  );
};
