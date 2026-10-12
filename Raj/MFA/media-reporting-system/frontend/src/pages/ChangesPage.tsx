import React, { useState, useEffect, useMemo } from 'react';
import { ContentChange } from '../types/dashboard';
import { changeService } from '../services/changeService';
import { DataTable, Column } from '../components/common/DataTable';
import { StatusBadge } from '../components/common/StatusBadge';
import { Search, SlidersHorizontal, History, RotateCcw } from 'lucide-react';

export const ChangesPage: React.FC = () => {
  const [changes, setChanges] = useState<ContentChange[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // Filters
  const [search, setSearch] = useState('');
  const [websiteFilter, setWebsiteFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');

  useEffect(() => {
    changeService.getAllChanges().then((data) => {
      setChanges(data);
      setIsLoading(false);
    });
  }, []);

  const filteredChanges = useMemo(() => {
    return changes.filter((chg) => {
      const matchSearch =
        !search ||
        chg.item.toLowerCase().includes(search.toLowerCase()) ||
        chg.change_description.toLowerCase().includes(search.toLowerCase());

      const matchWebsite =
        websiteFilter === 'all' || chg.website.toLowerCase().includes(websiteFilter.toLowerCase());

      const matchType = typeFilter === 'all' || chg.type === typeFilter;
      const matchStatus = statusFilter === 'all' || chg.status === statusFilter;

      return matchSearch && matchWebsite && matchType && matchStatus;
    });
  }, [changes, search, websiteFilter, typeFilter, statusFilter]);

  const handleResetFilters = () => {
    setSearch('');
    setWebsiteFilter('all');
    setTypeFilter('all');
    setStatusFilter('all');
  };

  const columns: Column<ContentChange>[] = [
    {
      key: 'timestamp',
      header: 'Detected Time',
      width: '135px',
      sortable: true,
      render: (row) => <span style={{ color: 'var(--text-muted)' }}>{row.timestamp}</span>,
    },
    {
      key: 'website',
      header: 'Source Website',
      width: '140px',
      sortable: true,
      render: (row) => <span style={{ fontWeight: 500 }}>{row.website}</span>,
    },
    {
      key: 'type',
      header: 'Change Category',
      width: '150px',
      sortable: true,
      render: (row) => <StatusBadge status={row.type} size="sm" />,
    },
    {
      key: 'item',
      header: 'Monitored Target Item',
      width: '240px',
      sortable: true,
      render: (row) => <span style={{ fontWeight: 600, color: 'var(--text-main)' }}>{row.item}</span>,
    },
    {
      key: 'change_description',
      header: 'Detected Content Alteration',
      render: (row) => (
        <span style={{ fontSize: '12.5px', color: 'var(--text-muted)' }}>
          {row.change_description}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      width: '110px',
      render: (row) => <StatusBadge status={row.status} size="sm" />,
    },
  ];

  return (
    <div>
      {/* Header */}
      <div className="section-header" style={{ marginBottom: '18px' }}>
        <div>
          <h1 style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-main)' }}>
            Content & Visual Change Feed
          </h1>
          <p style={{ fontSize: '13.5px', color: 'var(--text-muted)' }}>
            Continuous diff engine logging editorial headline edits, layout alterations, and flight removals
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
          {filteredChanges.length} Events Detected
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
          <div style={{ position: 'relative', width: '280px' }}>
            <Search
              size={14}
              style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }}
            />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search target item, description..."
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

          <select
            value={websiteFilter}
            onChange={(e) => setWebsiteFilter(e.target.value)}
            className="filter-select"
          >
            <option value="all">All Websites</option>
            <option value="ET BrandEquity">ET BrandEquity</option>
            <option value="Exchange4media">Exchange4media</option>
          </select>

          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="filter-select"
          >
            <option value="all">All Change Types</option>
            <option value="NEW ARTICLE">NEW ARTICLE</option>
            <option value="ARTICLE UPDATED">ARTICLE UPDATED</option>
            <option value="NEW AD">NEW AD</option>
            <option value="AD CHANGED">AD CHANGED</option>
            <option value="AD REMOVED">AD REMOVED</option>
          </select>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="filter-select"
          >
            <option value="all">All Statuses</option>
            <option value="ACTIVE">ACTIVE</option>
            <option value="ARCHIVED">ARCHIVED</option>
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

      {/* Changes Data Table */}
      <DataTable
        columns={columns}
        data={filteredChanges}
        keyExtractor={(c) => c.id}
        isLoading={isLoading}
        emptyTitle="No change records detected"
        emptyDescription="All tracked pages and campaigns are currently synchronized without diffs."
        pageSize={8}
      />
    </div>
  );
};
