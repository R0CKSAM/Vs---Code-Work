import React, { useState, useEffect, useCallback } from 'react';
import { CustomReportResponse, ExportFormat } from '../types/reports';
import { reportService } from '../services/reportService';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import {
  Sliders,
  Calendar,
  Search,
  FileDown,
  FileSpreadsheet,
  FileText,
  Filter,
  RefreshCw,
  ExternalLink,
  AlertCircle,
  Building2,
  Layers,
  Sparkles,
  BookOpen,
} from 'lucide-react';

export const CustomReportPage: React.FC = () => {
  const [startDate, setStartDate] = useState<string>('2026-09-01');
  const [endDate, setEndDate] = useState<string>('2026-09-23');
  const [selectedWebsite, setSelectedWebsite] = useState<string>('all');
  const [selectedSection, setSelectedSection] = useState<string>('all');
  const [selectedStatus, setSelectedStatus] = useState<string>('ALL');
  const [searchKeyword, setSearchKeyword] = useState<string>('');
  const [resultLimit, setResultLimit] = useState<number>(500);

  const [report, setReport] = useState<CustomReportResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [exportingFormat, setExportingFormat] = useState<ExportFormat | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [feedbackNotice, setFeedbackNotice] = useState<{ text: string; type: 'info' | 'success' | 'error' } | null>(null);

  const loadCustomReport = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const data = await reportService.getCustomReport({
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        website: selectedWebsite !== 'all' ? selectedWebsite : undefined,
        section: selectedSection !== 'all' ? selectedSection : undefined,
        status: selectedStatus !== 'ALL' ? selectedStatus : undefined,
        search: searchKeyword.trim() || undefined,
        limit: resultLimit,
      });
      setReport(data);
    } catch (err: any) {
      console.error('Failed to load custom report:', err);
      setErrorMessage(err.message || 'Failed to generate custom dossier from backend API');
    } finally {
      setIsLoading(false);
    }
  }, [startDate, endDate, selectedWebsite, selectedSection, selectedStatus, searchKeyword, resultLimit]);

  useEffect(() => {
    loadCustomReport();
  }, [loadCustomReport]);

  const handleExport = async (format: ExportFormat) => {
    setExportingFormat(format);
    setFeedbackNotice({ text: `Compiling and downloading custom ${format.toUpperCase()} dossier...`, type: 'info' });
    try {
      await reportService.exportReport({
        report_type: 'custom',
        format,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        website: selectedWebsite !== 'all' ? selectedWebsite : undefined,
        section: selectedSection !== 'all' ? selectedSection : undefined,
        status: selectedStatus !== 'ALL' ? selectedStatus : undefined,
        search: searchKeyword.trim() || undefined,
      });
      setFeedbackNotice({ text: `Successfully generated custom ${format.toUpperCase()} export.`, type: 'success' });
      setTimeout(() => setFeedbackNotice(null), 4000);
    } catch (err: any) {
      setFeedbackNotice({ text: `Export failed: ${err.message}`, type: 'error' });
    } finally {
      setExportingFormat(null);
    }
  };

  return (
    <div>
      {/* Feedback Notice */}
      {feedbackNotice && (
        <div
          style={{
            padding: '10px 16px',
            backgroundColor:
              feedbackNotice.type === 'error'
                ? '#fef2f2'
                : feedbackNotice.type === 'success'
                ? '#f0fdf4'
                : '#eff6ff',
            border: `1px solid ${
              feedbackNotice.type === 'error'
                ? '#fecaca'
                : feedbackNotice.type === 'success'
                ? '#bbf7d0'
                : '#bfdbfe'
            }`,
            borderRadius: 'var(--radius-sm)',
            color:
              feedbackNotice.type === 'error'
                ? '#b91c1c'
                : feedbackNotice.type === 'success'
                ? '#15803d'
                : '#1d4ed8',
            fontSize: '13px',
            marginBottom: '16px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          {feedbackNotice.type === 'error' ? <AlertCircle size={15} /> : <Sparkles size={15} />}
          <span>{feedbackNotice.text}</span>
        </div>
      )}

      {errorMessage && (
        <div
          style={{
            padding: '12px 16px',
            backgroundColor: '#fef2f2',
            border: '1px solid #f87171',
            borderRadius: 'var(--radius-sm)',
            color: '#991b1b',
            fontSize: '13px',
            marginBottom: '16px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <AlertCircle size={16} />
            <span>{errorMessage}</span>
          </div>
          <button
            onClick={loadCustomReport}
            style={{
              padding: '4px 10px',
              backgroundColor: '#ffffff',
              border: '1px solid #f87171',
              borderRadius: 'var(--radius-xs)',
              fontSize: '12px',
              fontWeight: 600,
              cursor: 'pointer',
              color: '#991b1b',
            }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: '16px',
          marginBottom: '20px',
        }}
      >
        <div>
          <h1 style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-main)' }}>
            Custom Report Dossier Builder
          </h1>
          <p style={{ fontSize: '13.5px', color: 'var(--text-muted)' }}>
            Filter and compile tailored intelligence dossiers across multi-dimensional parameters with instant exports
          </p>
        </div>

        {/* Global Export Buttons */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button
            onClick={() => handleExport('pdf')}
            disabled={isLoading || exportingFormat !== null}
            style={{
              padding: '7px 12px',
              backgroundColor: '#ffffff',
              border: '1px solid var(--border-light)',
              color: 'var(--text-main)',
              borderRadius: 'var(--radius-sm)',
              fontSize: '12.5px',
              fontWeight: 500,
              display: 'inline-flex',
              alignItems: 'center',
              gap: '5px',
              cursor: isLoading || exportingFormat !== null ? 'not-allowed' : 'pointer',
              opacity: exportingFormat === 'pdf' ? 0.6 : 1,
            }}
          >
            <FileDown size={13} />
            <span>{exportingFormat === 'pdf' ? 'Exporting...' : 'Export PDF'}</span>
          </button>

          <button
            onClick={() => handleExport('excel')}
            disabled={isLoading || exportingFormat !== null}
            style={{
              padding: '7px 12px',
              backgroundColor: '#ffffff',
              border: '1px solid var(--border-light)',
              color: 'var(--text-main)',
              borderRadius: 'var(--radius-sm)',
              fontSize: '12.5px',
              fontWeight: 500,
              display: 'inline-flex',
              alignItems: 'center',
              gap: '5px',
              cursor: isLoading || exportingFormat !== null ? 'not-allowed' : 'pointer',
              opacity: exportingFormat === 'excel' ? 0.6 : 1,
            }}
          >
            <FileSpreadsheet size={13} />
            <span>{exportingFormat === 'excel' ? 'Exporting...' : 'Export Excel'}</span>
          </button>

          <button
            onClick={() => handleExport('csv')}
            disabled={isLoading || exportingFormat !== null}
            style={{
              padding: '7px 12px',
              backgroundColor: '#ffffff',
              border: '1px solid var(--border-light)',
              color: 'var(--text-main)',
              borderRadius: 'var(--radius-sm)',
              fontSize: '12.5px',
              fontWeight: 500,
              display: 'inline-flex',
              alignItems: 'center',
              gap: '5px',
              cursor: isLoading || exportingFormat !== null ? 'not-allowed' : 'pointer',
              opacity: exportingFormat === 'csv' ? 0.6 : 1,
            }}
          >
            <FileText size={13} />
            <span>{exportingFormat === 'csv' ? 'Exporting...' : 'Export CSV'}</span>
          </button>
        </div>
      </div>

      {/* Filter Parameters Form */}
      <div
        style={{
          backgroundColor: '#ffffff',
          border: '1px solid var(--border-light)',
          borderRadius: 'var(--radius-md)',
          padding: '20px',
          marginBottom: '24px',
          boxShadow: 'var(--shadow-card)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '14px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '16px' }}>
          <Sliders size={16} color="var(--accent-primary)" />
          <span>Parametric Filtering Criteria</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '14px' }}>
          {/* Start Date */}
          <div>
            <label style={{ display: 'block', fontSize: '11.5px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '4px' }}>
              START DATE
            </label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              style={{
                width: '100%',
                height: '36px',
                padding: '0 8px',
                border: '1px solid var(--border-light)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '12.5px',
              }}
            />
          </div>

          {/* End Date */}
          <div>
            <label style={{ display: 'block', fontSize: '11.5px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '4px' }}>
              END DATE
            </label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              style={{
                width: '100%',
                height: '36px',
                padding: '0 8px',
                border: '1px solid var(--border-light)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '12.5px',
              }}
            />
          </div>

          {/* Publisher */}
          <div>
            <label style={{ display: 'block', fontSize: '11.5px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '4px' }}>
              PUBLICATION
            </label>
            <select
              value={selectedWebsite}
              onChange={(e) => setSelectedWebsite(e.target.value)}
              style={{
                width: '100%',
                height: '36px',
                padding: '0 8px',
                border: '1px solid var(--border-light)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '12.5px',
                backgroundColor: '#ffffff',
              }}
            >
              <option value="all">All Publishers</option>
              <option value="et_brand_equity">ET BrandEquity</option>
              <option value="exchange4media">Exchange4media</option>
            </select>
          </div>

          {/* Status */}
          <div>
            <label style={{ display: 'block', fontSize: '11.5px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '4px' }}>
              STATUS
            </label>
            <select
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              style={{
                width: '100%',
                height: '36px',
                padding: '0 8px',
                border: '1px solid var(--border-light)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '12.5px',
                backgroundColor: '#ffffff',
              }}
            >
              <option value="ALL">All Statuses</option>
              <option value="ACTIVE">Active Articles</option>
              <option value="UPDATED">Updated / Edited</option>
              <option value="REMOVED">Removed Articles</option>
            </select>
          </div>

          {/* Keyword Search */}
          <div>
            <label style={{ display: 'block', fontSize: '11.5px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '4px' }}>
              KEYWORD SEARCH
            </label>
            <div style={{ position: 'relative' }}>
              <input
                type="text"
                placeholder="e.g. AI, campaign, CEO..."
                value={searchKeyword}
                onChange={(e) => setSearchKeyword(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && loadCustomReport()}
                style={{
                  width: '100%',
                  height: '36px',
                  padding: '0 28px 0 8px',
                  border: '1px solid var(--border-light)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '12.5px',
                }}
              />
              <Search
                size={14}
                color="var(--text-muted)"
                style={{ position: 'absolute', right: '8px', top: '11px', pointerEvents: 'none' }}
              />
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '16px' }}>
          <button
            onClick={loadCustomReport}
            disabled={isLoading}
            style={{
              padding: '8px 18px',
              backgroundColor: 'var(--accent-primary)',
              color: '#ffffff',
              borderRadius: 'var(--radius-sm)',
              fontSize: '13px',
              fontWeight: 600,
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              border: 'none',
              cursor: isLoading ? 'not-allowed' : 'pointer',
            }}
          >
            <Filter size={14} />
            <span>Apply Filters</span>
          </button>
        </div>
      </div>

      {isLoading ? (
        <div style={{ padding: '24px 0' }}>
          <LoadingSkeleton rows={5} height={90} />
        </div>
      ) : report ? (
        <>
          {/* Summary KPIs */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(4, 1fr)',
              gap: '14px',
              marginBottom: '24px',
            }}
          >
            <div
              style={{
                backgroundColor: '#ffffff',
                border: '1px solid var(--border-light)',
                padding: '16px 20px',
                borderRadius: 'var(--radius-md)',
                boxShadow: 'var(--shadow-card)',
              }}
            >
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 500 }}>Matching Articles</div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-main)', marginTop: '4px' }}>
                {report.total_matching}
              </div>
              <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '2px' }}>
                Matching selected criteria
              </div>
            </div>

            <div
              style={{
                backgroundColor: '#ffffff',
                border: '1px solid var(--border-light)',
                padding: '16px 20px',
                borderRadius: 'var(--radius-md)',
                boxShadow: 'var(--shadow-card)',
              }}
            >
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 500 }}>Active Status Count</div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#047857', marginTop: '4px' }}>
                {report.status_breakdown['ACTIVE'] || 0}
              </div>
              <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '2px' }}>
                Currently indexed
              </div>
            </div>

            <div
              style={{
                backgroundColor: '#ffffff',
                border: '1px solid var(--border-light)',
                padding: '16px 20px',
                borderRadius: 'var(--radius-md)',
                boxShadow: 'var(--shadow-card)',
              }}
            >
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 500 }}>Updated Count</div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#b45309', marginTop: '4px' }}>
                {report.status_breakdown['UPDATED'] || 0}
              </div>
              <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '2px' }}>
                With headline/content revisions
              </div>
            </div>

            <div
              style={{
                backgroundColor: '#ffffff',
                border: '1px solid var(--border-light)',
                padding: '16px 20px',
                borderRadius: 'var(--radius-md)',
                boxShadow: 'var(--shadow-card)',
              }}
            >
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 500 }}>Categories Represented</div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#0284c7', marginTop: '4px' }}>
                {report.section_breakdown.length}
              </div>
              <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '2px' }}>
                Across {report.publisher_breakdown.length} publishers
              </div>
            </div>
          </div>

          {/* Breakdown Tables */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '24px' }}>
            {/* Publisher Distribution */}
            <div
              style={{
                backgroundColor: '#ffffff',
                border: '1px solid var(--border-light)',
                borderRadius: 'var(--radius-md)',
                padding: '20px',
                boxShadow: 'var(--shadow-card)',
              }}
            >
              <h2 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Building2 size={16} color="var(--accent-primary)" />
                Publisher Breakdown
              </h2>
              {report.publisher_breakdown.length === 0 ? (
                <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>No publisher matches found.</p>
              ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12.5px' }}>
                  <thead>
                    <tr style={{ backgroundColor: 'var(--bg-surface-subtle)', borderBottom: '1px solid var(--border-light)' }}>
                      <th style={{ padding: '8px 10px', color: 'var(--text-muted)', fontSize: '11px', textTransform: 'uppercase' }}>Publisher</th>
                      <th style={{ padding: '8px 10px', color: 'var(--text-muted)', fontSize: '11px', textTransform: 'uppercase' }}>Articles</th>
                      <th style={{ padding: '8px 10px', color: 'var(--text-muted)', fontSize: '11px', textTransform: 'uppercase' }}>Share</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.publisher_breakdown.map((p, idx) => (
                      <tr key={idx} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                        <td style={{ padding: '10px', fontWeight: 600 }}>{p.website_name}</td>
                        <td style={{ padding: '10px' }}>{p.article_count}</td>
                        <td style={{ padding: '10px', color: 'var(--accent-primary)', fontWeight: 600 }}>{p.percentage}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* Section Breakdown */}
            <div
              style={{
                backgroundColor: '#ffffff',
                border: '1px solid var(--border-light)',
                borderRadius: 'var(--radius-md)',
                padding: '20px',
                boxShadow: 'var(--shadow-card)',
              }}
            >
              <h2 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Layers size={16} color="var(--accent-primary)" />
                Section Breakdown ({report.section_breakdown.length})
              </h2>
              {report.section_breakdown.length === 0 ? (
                <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>No section matches found.</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '200px', overflowY: 'auto' }}>
                  {report.section_breakdown.map((s, idx) => (
                    <div
                      key={idx}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        padding: '8px 12px',
                        backgroundColor: 'var(--bg-surface-subtle)',
                        borderRadius: 'var(--radius-xs)',
                        border: '1px solid var(--border-light)',
                      }}
                    >
                      <span style={{ fontSize: '13px', fontWeight: 500 }}>{s.section_name} ({s.website_name})</span>
                      <span style={{ fontSize: '13px', fontWeight: 700 }}>{s.article_count} articles</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Matching Articles List */}
          <div
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid var(--border-light)',
              borderRadius: 'var(--radius-md)',
              padding: '22px',
              boxShadow: 'var(--shadow-card)',
            }}
          >
            <h2 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <BookOpen size={18} color="var(--accent-primary)" />
              Filtered Intelligence Dossier Records ({report.articles.length})
            </h2>

            {report.articles.length === 0 ? (
              <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13.5px' }}>
                No articles found matching the specified parameters. Try expanding your date range or adjusting keywords.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {report.articles.map((art) => (
                  <div
                    key={art.id}
                    style={{
                      padding: '14px 16px',
                      backgroundColor: '#ffffff',
                      borderRadius: 'var(--radius-sm)',
                      border: '1px solid var(--border-light)',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span
                          style={{
                            fontSize: '11px',
                            fontWeight: 600,
                            padding: '2px 8px',
                            borderRadius: '4px',
                            backgroundColor:
                              art.website_key === 'et_brand_equity' ? '#eff6ff' : '#fdf2f8',
                            color:
                              art.website_key === 'et_brand_equity' ? '#1d4ed8' : '#be185d',
                          }}
                        >
                          {art.website_name}
                        </span>
                        <span style={{ fontSize: '11.5px', color: 'var(--text-muted)' }}>
                          {art.section_name}
                        </span>
                        <span
                          style={{
                            fontSize: '10.5px',
                            fontWeight: 600,
                            padding: '1px 6px',
                            borderRadius: '3px',
                            backgroundColor:
                              art.status === 'ACTIVE'
                                ? '#ecfdf5'
                                : art.status === 'UPDATED'
                                ? '#fffbeb'
                                : '#fef2f2',
                            color:
                              art.status === 'ACTIVE'
                                ? '#047857'
                                : art.status === 'UPDATED'
                                ? '#b45309'
                                : '#b91c1c',
                          }}
                        >
                          {art.status}
                        </span>
                      </div>
                      <span style={{ fontSize: '11.5px', color: 'var(--text-muted)' }}>
                        {art.published_at ? art.published_at.slice(0, 10) : 'Indexed'}
                      </span>
                    </div>

                    <a
                      href={art.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        fontSize: '14px',
                        fontWeight: 600,
                        color: 'var(--text-main)',
                        textDecoration: 'none',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        marginBottom: '4px',
                      }}
                    >
                      <span>{art.headline}</span>
                      <ExternalLink size={12} color="var(--text-muted)" />
                    </a>

                    {art.summary && (
                      <p style={{ fontSize: '12.5px', color: 'var(--text-muted)', lineHeight: 1.4, margin: 0 }}>
                        {art.summary}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
};
