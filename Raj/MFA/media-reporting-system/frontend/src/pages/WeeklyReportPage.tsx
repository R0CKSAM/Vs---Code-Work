import React, { useState, useEffect, useCallback } from 'react';
import { WeeklyReportResponse, ExportFormat } from '../types/reports';
import { reportService } from '../services/reportService';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import {
  Calendar,
  FileDown,
  FileSpreadsheet,
  FileText,
  RefreshCw,
  TrendingUp,
  AlertCircle,
  ExternalLink,
  BarChart3,
  Building2,
  Layers,
  Sparkles,
} from 'lucide-react';

export const WeeklyReportPage: React.FC = () => {
  const [report, setReport] = useState<WeeklyReportResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [startDate, setStartDate] = useState<string>('2026-09-17');
  const [endDate, setEndDate] = useState<string>('2026-09-23');
  const [exportingFormat, setExportingFormat] = useState<ExportFormat | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [feedbackNotice, setFeedbackNotice] = useState<{ text: string; type: 'info' | 'success' | 'error' } | null>(null);

  const loadWeeklyReport = useCallback(async (sDate: string, eDate: string) => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const data = await reportService.getWeeklyReport(sDate, eDate);
      setReport(data);
    } catch (err: any) {
      console.error('Failed to load weekly report:', err);
      setErrorMessage(err.message || 'Failed to generate weekly report from backend API');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadWeeklyReport(startDate, endDate);
  }, [loadWeeklyReport, startDate, endDate]);

  const handleExport = async (format: ExportFormat) => {
    setExportingFormat(format);
    setFeedbackNotice({ text: `Compiling and downloading ${format.toUpperCase()} report...`, type: 'info' });
    try {
      await reportService.exportReport({
        report_type: 'weekly',
        format,
        start_date: startDate,
        end_date: endDate,
      });
      setFeedbackNotice({ text: `Successfully generated ${format.toUpperCase()} export file.`, type: 'success' });
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
            onClick={() => loadWeeklyReport(startDate, endDate)}
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

      {/* Header & Controls */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: '16px',
          marginBottom: '22px',
        }}
      >
        <div>
          <h1 style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-main)' }}>
            Weekly Industry Roll-up
          </h1>
          <p style={{ fontSize: '13.5px', color: 'var(--text-muted)' }}>
            Aggregate weekly market coverage, multi-portal comparative analytics, and daily publication trends
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          {/* Start Date */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Calendar size={14} color="var(--text-muted)" />
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>From:</span>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              style={{
                height: '34px',
                padding: '0 8px',
                border: '1px solid var(--border-light)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '12.5px',
                backgroundColor: '#ffffff',
              }}
            />
          </div>

          {/* End Date */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>To:</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              style={{
                height: '34px',
                padding: '0 8px',
                border: '1px solid var(--border-light)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '12.5px',
                backgroundColor: '#ffffff',
              }}
            />
          </div>

          <button
            onClick={() => loadWeeklyReport(startDate, endDate)}
            disabled={isLoading}
            style={{
              padding: '7px 12px',
              backgroundColor: 'var(--accent-primary)',
              color: '#ffffff',
              borderRadius: 'var(--radius-sm)',
              fontSize: '12.5px',
              fontWeight: 500,
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              border: 'none',
              cursor: isLoading ? 'not-allowed' : 'pointer',
              opacity: isLoading ? 0.7 : 1,
            }}
          >
            <RefreshCw size={13} className={isLoading ? 'animate-spin' : ''} />
            <span>Generate Roll-up</span>
          </button>

          {/* Export Controls */}
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
            <span>{exportingFormat === 'pdf' ? 'Exporting...' : 'PDF'}</span>
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
            <span>{exportingFormat === 'excel' ? 'Exporting...' : 'Excel'}</span>
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
            <span>{exportingFormat === 'csv' ? 'Exporting...' : 'CSV'}</span>
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
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 500 }}>
                Total Articles (Range)
              </div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-main)', marginTop: '4px' }}>
                {report.total_articles}
              </div>
              <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '2px' }}>
                {report.date_range.start_date} to {report.date_range.end_date}
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
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 500 }}>
                ET BrandEquity Articles
              </div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#1d4ed8', marginTop: '4px' }}>
                {report.et_article_count}
              </div>
              <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '2px' }}>
                {report.total_articles > 0 ? ((report.et_article_count / report.total_articles) * 100).toFixed(1) : 0}% of weekly volume
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
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 500 }}>
                Exchange4media Articles
              </div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#be185d', marginTop: '4px' }}>
                {report.e4m_article_count}
              </div>
              <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '2px' }}>
                {report.total_articles > 0 ? ((report.e4m_article_count / report.total_articles) * 100).toFixed(1) : 0}% of weekly volume
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
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 500 }}>
                Covered Sections
              </div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#047857', marginTop: '4px' }}>
                {report.sections_count}
              </div>
              <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '2px' }}>
                {report.new_articles_count} new entries detected
              </div>
            </div>
          </div>

          {/* Daily Volume Progression Table */}
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
            <h2 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <BarChart3 size={16} color="var(--accent-primary)" />
              Daily Volume Progression Matrix (ET vs Exchange4media)
            </h2>

            {report.daily_volume.length === 0 ? (
              <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>No daily activity logged in this timeframe.</p>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
                <thead>
                  <tr style={{ backgroundColor: 'var(--bg-surface-subtle)', borderBottom: '1px solid var(--border-light)' }}>
                    <th style={{ padding: '10px 14px', color: 'var(--text-muted)', textTransform: 'uppercase', fontSize: '11.5px' }}>Date</th>
                    <th style={{ padding: '10px 14px', color: '#1d4ed8', textTransform: 'uppercase', fontSize: '11.5px' }}>ET BrandEquity</th>
                    <th style={{ padding: '10px 14px', color: '#be185d', textTransform: 'uppercase', fontSize: '11.5px' }}>Exchange4media</th>
                    <th style={{ padding: '10px 14px', color: 'var(--text-main)', textTransform: 'uppercase', fontSize: '11.5px' }}>Combined Total</th>
                    <th style={{ padding: '10px 14px', color: 'var(--text-muted)', textTransform: 'uppercase', fontSize: '11.5px' }}>Visual Share</th>
                  </tr>
                </thead>
                <tbody>
                  {report.daily_volume.map((vol, idx) => (
                    <tr key={idx} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <td style={{ padding: '12px 14px', fontWeight: 600 }}>{vol.date}</td>
                      <td style={{ padding: '12px 14px', color: '#1d4ed8', fontWeight: 600 }}>{vol.et_count}</td>
                      <td style={{ padding: '12px 14px', color: '#be185d', fontWeight: 600 }}>{vol.e4m_count}</td>
                      <td style={{ padding: '12px 14px', fontWeight: 700 }}>{vol.total_count}</td>
                      <td style={{ padding: '12px 14px', width: '220px' }}>
                        <div style={{ height: '8px', backgroundColor: '#e2e8f0', borderRadius: '4px', overflow: 'hidden', display: 'flex' }}>
                          <div
                            style={{
                              height: '100%',
                              width: vol.total_count > 0 ? `${(vol.et_count / vol.total_count) * 100}%` : '0%',
                              backgroundColor: '#3b82f6',
                            }}
                          />
                          <div
                            style={{
                              height: '100%',
                              width: vol.total_count > 0 ? `${(vol.e4m_count / vol.total_count) * 100}%` : '0%',
                              backgroundColor: '#ec4899',
                            }}
                          />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Publisher & Section Summaries */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '24px' }}>
            {/* Publisher Aggregation */}
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
                Publisher Totals & Churn
              </h2>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12.5px' }}>
                <thead>
                  <tr style={{ backgroundColor: 'var(--bg-surface-subtle)', borderBottom: '1px solid var(--border-light)' }}>
                    <th style={{ padding: '8px 10px', color: 'var(--text-muted)', fontSize: '11px', textTransform: 'uppercase' }}>Publisher</th>
                    <th style={{ padding: '8px 10px', color: 'var(--text-muted)', fontSize: '11px', textTransform: 'uppercase' }}>Articles</th>
                    <th style={{ padding: '8px 10px', color: 'var(--text-muted)', fontSize: '11px', textTransform: 'uppercase' }}>Share</th>
                    <th style={{ padding: '8px 10px', color: 'var(--text-muted)', fontSize: '11px', textTransform: 'uppercase' }}>New</th>
                    <th style={{ padding: '8px 10px', color: 'var(--text-muted)', fontSize: '11px', textTransform: 'uppercase' }}>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {report.publisher_breakdown.map((p, idx) => (
                    <tr key={idx} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <td style={{ padding: '10px', fontWeight: 600 }}>{p.website_name}</td>
                      <td style={{ padding: '10px' }}>{p.article_count}</td>
                      <td style={{ padding: '10px', color: 'var(--accent-primary)', fontWeight: 600 }}>{p.percentage}%</td>
                      <td style={{ padding: '10px', color: '#047857' }}>+{p.new_count}</td>
                      <td style={{ padding: '10px', color: '#b45309' }}>{p.updated_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
                Section Aggregation ({report.section_breakdown.length})
              </h2>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxHeight: '240px', overflowY: 'auto' }}>
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
                    <div>
                      <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)' }}>{s.section_name}</div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{s.website_name}</div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-main)' }}>{s.article_count} articles</div>
                      <div style={{ fontSize: '11px', color: '#047857' }}>+{s.new_count} new</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Top Stories */}
          <div
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid var(--border-light)',
              borderRadius: 'var(--radius-md)',
              padding: '22px',
              boxShadow: 'var(--shadow-card)',
            }}
          >
            <h2 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '16px' }}>
              Prominent Stories This Week ({report.top_stories.length})
            </h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {report.top_stories.map((story) => (
                <div
                  key={story.id}
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
                            story.website_key === 'et_brand_equity' ? '#eff6ff' : '#fdf2f8',
                          color:
                            story.website_key === 'et_brand_equity' ? '#1d4ed8' : '#be185d',
                        }}
                      >
                        {story.website_name}
                      </span>
                      <span style={{ fontSize: '11.5px', color: 'var(--text-muted)' }}>
                        {story.section_name}
                      </span>
                    </div>
                    <span style={{ fontSize: '11.5px', color: 'var(--text-muted)' }}>
                      {story.published_at ? story.published_at.slice(0, 10) : 'Recent'}
                    </span>
                  </div>

                  <a
                    href={story.url}
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
                    <span>{story.headline}</span>
                    <ExternalLink size={12} color="var(--text-muted)" />
                  </a>

                  {story.summary && (
                    <p style={{ fontSize: '12.5px', color: 'var(--text-muted)', lineHeight: 1.4, margin: 0 }}>
                      {story.summary}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
};
