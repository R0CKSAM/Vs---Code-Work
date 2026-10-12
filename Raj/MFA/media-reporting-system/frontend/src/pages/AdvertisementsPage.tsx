import React, { useState, useEffect, useMemo } from 'react';
import { Advertisement } from '../types/dashboard';
import { advertisementService } from '../services/advertisementService';
import { DataTable, Column } from '../components/common/DataTable';
import { StatusBadge } from '../components/common/StatusBadge';
import { AdvertisementDetailDrawer } from '../components/advertisements/AdvertisementDetailDrawer';
import { Search, SlidersHorizontal, Image, Eye, RotateCcw, Megaphone, CheckCircle2, History, Layers } from 'lucide-react';

interface AdvertisementsPageProps {
  initialAdId?: string | null;
}

export const AdvertisementsPage: React.FC<AdvertisementsPageProps> = ({ initialAdId }) => {
  const [ads, setAds] = useState<Advertisement[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState('');
  const [websiteFilter, setWebsiteFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');

  const [selectedAd, setSelectedAd] = useState<Advertisement | null>(null);

  useEffect(() => {
    advertisementService.getAllAdvertisements().then((data) => {
      setAds(data);
      setIsLoading(false);

      if (initialAdId) {
        const found = data.find((a) => a.id === initialAdId);
        if (found) setSelectedAd(found);
      }
    }).catch((err: Error) => { setError(err.message); setIsLoading(false); });
  }, [initialAdId]);

  const filteredAds = useMemo(() => {
    return ads.filter((ad) => {
      const adv = (ad.advertiser || '').toLowerCase();
      const brd = (ad.brand || '').toLowerCase();
      const cmp = (ad.campaign || '').toLowerCase();
      const pos = (ad.position || '').toLowerCase();
      const q = search.toLowerCase();

      const matchSearch = !search || adv.includes(q) || brd.includes(q) || cmp.includes(q) || pos.includes(q);
      const matchWebsite = websiteFilter === 'all' || ad.website.toLowerCase().includes(websiteFilter.toLowerCase()) || ad.website_id.toLowerCase().includes(websiteFilter.toLowerCase());
      const matchStatus = statusFilter === 'all' || ad.status === statusFilter;

      return matchSearch && matchWebsite && matchStatus;
    });
  }, [ads, search, websiteFilter, statusFilter]);

  // Real-time KPI aggregations derived from actual data
  const kpis = useMemo(() => {
    const total = ads.length;
    const active = ads.filter((a) => a.status === 'ACTIVE' || a.status === 'NEW').length;
    const changed = ads.filter((a) => a.status === 'CHANGED').length;
    const identifiedBrands = new Set(ads.map((a) => a.brand).filter(Boolean)).size;
    const identifiedAdvertisers = new Set(ads.map((a) => a.advertiser).filter(Boolean)).size;
    return { total, active, changed, identifiedBrands, identifiedAdvertisers };
  }, [ads]);

  const handleResetFilters = () => {
    setSearch('');
    setWebsiteFilter('all');
    setStatusFilter('all');
  };

  const columns: Column<Advertisement>[] = [
    {
      key: 'advertiser',
      header: 'Advertiser & Brand',
      width: '180px',
      sortable: true,
      render: (row) => (
        <div>
          <div style={{ fontWeight: 600, color: 'var(--text-main)' }}>
            {row.advertiser || <span style={{ color: 'var(--text-subtle)', fontStyle: 'italic' }}>Not identified</span>}
          </div>
          <div style={{ fontSize: '11.5px', color: 'var(--text-muted)' }}>
            {row.brand || <span style={{ color: 'var(--text-subtle)', fontStyle: 'italic' }}>Not identified</span>}
          </div>
        </div>
      ),
    },
    {
      key: 'campaign',
      header: 'Campaign / Creative',
      sortable: true,
      render: (row) => (
        <span style={{ fontWeight: 500, color: 'var(--text-main)', fontSize: '12.5px' }}>
          {row.campaign ? `“${row.campaign}”` : <span style={{ color: 'var(--text-muted)' }}>Placement Ad Unit</span>}
        </span>
      ),
    },
    {
      key: 'website',
      header: 'Publisher',
      width: '140px',
      sortable: true,
      render: (row) => (
        <span style={{ fontSize: '12.5px', color: 'var(--text-muted)' }}>{row.website}</span>
      ),
    },
    {
      key: 'section_page',
      header: 'Section',
      width: '120px',
      render: (row) => (
        <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{row.section_page}</span>
      ),
    },
    {
      key: 'position',
      header: 'Detected Placement',
      width: '210px',
      render: (row) => (
        <span style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
          {row.position}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      width: '105px',
      sortable: true,
      render: (row) => <StatusBadge status={row.status} size="sm" />,
    },
    {
      key: 'first_seen',
      header: 'First Seen',
      width: '130px',
      render: (row) => <span style={{ fontSize: '11.5px', color: 'var(--text-muted)' }}>{row.first_seen}</span>,
    },
    {
      key: 'screenshot',
      header: 'Creative Asset',
      width: '100px',
      align: 'center',
      render: (row) => (
        <div style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
          {row.screenshot_url ? (
            <img
              src={row.screenshot_url}
              alt="Creative Preview"
              style={{
                width: '32px',
                height: '32px',
                objectFit: 'cover',
                borderRadius: 'var(--radius-xs)',
                border: '1px solid var(--border-light)',
              }}
              onError={(e) => {
                (e.target as HTMLElement).style.display = 'none';
              }}
            />
          ) : (
            <div
              style={{
                width: '28px',
                height: '28px',
                borderRadius: 'var(--radius-xs)',
                backgroundColor: 'var(--bg-surface-subtle)',
                border: '1px solid var(--border-light)',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--text-subtle)',
              }}
              title="Creative URL or iframe unit tracked"
            >
              <Image size={14} />
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      width: '85px',
      align: 'right',
      render: (row) => (
        <button
          onClick={(e) => {
            e.stopPropagation();
            setSelectedAd(row);
          }}
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
            cursor: 'pointer',
          }}
        >
          <Eye size={12} />
          <span>Details</span>
        </button>
      ),
    },
  ];

  return (
    <div>
      {error && <p role="alert">Unable to load live data: {error}</p>}
      {/* Header */}
      <div className="section-header" style={{ marginBottom: '18px' }}>
        <div>
          <h1 style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-main)' }}>
            Live Advertisement Monitoring
          </h1>
          <p style={{ fontSize: '13.5px', color: 'var(--text-muted)' }}>
            Competitive digital advertising intelligence across mastheads, responsive display units, and sponsored slots
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
          {filteredAds.length} Placements Tracked
        </span>
      </div>

      {/* KPI Cards Row */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: '14px',
          marginBottom: '20px',
        }}
      >
        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--border-light)',
            borderRadius: 'var(--radius-md)',
            padding: '14px 16px',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Total Tracked Ads
          </div>
          <div style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-main)', marginTop: '4px' }}>
            {kpis.total}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-subtle)', marginTop: '2px' }}>
            Across all monitored publishers
          </div>
        </div>

        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--border-light)',
            borderRadius: 'var(--radius-md)',
            padding: '14px 16px',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Active Placements
          </div>
          <div style={{ fontSize: '22px', fontWeight: 700, color: '#047857', marginTop: '4px' }}>
            {kpis.active}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-subtle)', marginTop: '2px' }}>
            Currently confirmed live in markup
          </div>
        </div>

        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--border-light)',
            borderRadius: 'var(--radius-md)',
            padding: '14px 16px',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Changed Creatives
          </div>
          <div style={{ fontSize: '22px', fontWeight: 700, color: '#b45309', marginTop: '4px' }}>
            {kpis.changed}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-subtle)', marginTop: '2px' }}>
            Slot creative revision events
          </div>
        </div>

        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--border-light)',
            borderRadius: 'var(--radius-md)',
            padding: '14px 16px',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Identified Brands / Advertisers
          </div>
          <div style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-main)', marginTop: '4px' }}>
            {kpis.identifiedBrands} <span style={{ fontSize: '14px', fontWeight: 400, color: 'var(--text-muted)' }}>Brands</span> / {kpis.identifiedAdvertisers} <span style={{ fontSize: '14px', fontWeight: 400, color: 'var(--text-muted)' }}>Adv</span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-subtle)', marginTop: '2px' }}>
            Authoritatively identified brands
          </div>
        </div>
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
              placeholder="Search advertiser, brand, placement..."
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
            <option value="all">All Publishers</option>
            <option value="ET BrandEquity">ET BrandEquity</option>
            <option value="Exchange4media">Exchange4media</option>
          </select>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="filter-select"
          >
            <option value="all">All Statuses</option>
            <option value="ACTIVE">ACTIVE</option>
            <option value="NEW">NEW</option>
            <option value="CHANGED">CHANGED</option>
            <option value="REMOVED">REMOVED</option>
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
            cursor: 'pointer',
            border: '1px solid var(--border-light)',
            backgroundColor: 'var(--bg-surface-subtle)',
          }}
        >
          <RotateCcw size={11} /> Reset
        </button>
      </div>

      {/* Ads Data Table */}
      <DataTable
        columns={columns}
        data={filteredAds}
        keyExtractor={(ad) => ad.id}
        onRowClick={(ad) => setSelectedAd(ad)}
        isLoading={isLoading}
        emptyTitle="No advertisements found"
        emptyDescription="Try clearing your search terms or selecting different publisher filters."
        pageSize={10}
        highlightedId={selectedAd?.id}
      />

      {/* Advertisement Detail Drawer */}
      <AdvertisementDetailDrawer
        ad={selectedAd}
        isOpen={Boolean(selectedAd)}
        onClose={() => setSelectedAd(null)}
      />
    </div>
  );
};
