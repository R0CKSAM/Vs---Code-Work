import React, { useState, useEffect, useCallback } from 'react';
import { DailyReportResponse, ExportFormat } from '../types/reports';
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
  ShieldCheck,
  Building2,
  Layers,
  Sparkles,
} from 'lucide-react';

export const DailyReportPage: React.FC = () => {
  const [report, setReport] = useState<DailyReportResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [selectedDate, setSelectedDate] = useState<string>('2026-09-23');
  const [exportingFormat, setExportingFormat] = useState<ExportFormat | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [feedbackNotice, setFeedbackNotice] = useState<{ text: string; type: 'info' | 'success' | 'error' } | null>(null);

  const loadDailyReport = useCallback(async (dateStr: string) => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const data = await reportService.getDailyReport(dateStr);
      setReport(data);
    } catch (err: any) {
      console.error('Failed to load daily report:', err);
      setErrorMessage(err.message || 'Failed to generate daily report from backend API');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDailyReport(selectedDate);
  }, [loadDailyReport, selectedDate]);

  const handleExport = async (format: ExportFormat) => {
    setExportingFormat(format);
    setFeedbackNotice({ text: `Compiling and downloading ${format.toUpperCase()} report...`, type: 'info' });
    try {
      await reportService.exportReport({
        report_type: 'daily',
        format,
        date: selectedDate,
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
      {/* Feedback & Error Notices */}
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
            onClick={() => loadDailyReport(selectedDate)}
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
            Daily Media Intelligence Brief
          </h1>
          <p style={{ fontSize: '13.5px', color: 'var(--text-muted)' }}>
            Consolidated executive digest covering breaking stories, publisher telemetry, and change tracking
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          {/* Date Picker */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Calendar size={14} color="var(--text-muted)" />
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
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
            onClick={() => loadDailyReport(selectedDate)}
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
            <span>Generate Report</span>
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
          {/* Summary KPI Row */}
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
                Total News Articles
              </div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-main)', marginTop: '4px' }}>
                {report.executive_summary.total_articles}
              </div>
              <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '2px' }}>
                ET: {report.executive_summary.et_article_count} | E4M: {report.executive_summary.e4m_article_count}
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
                New Ingested Articles
              </div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#047857', marginTop: '4px' }}>
                {report.executive_summary.new_articles_count}
              </div>
              <div style={{ fontSize: '11.5px', color: '#047857', marginTop: '2px', display: 'flex', alignItems: 'center', gap: '3px' }}>
                <TrendingUp size={12} /> Detected on {report.executive_summary.reporting_date}
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
                Updated & Altered Articles
              </div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#b45309', marginTop: '4px' }}>
                {report.executive_summary.updated_articles_count}
              </div>
              <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '2px' }}>
                Removed: {report.executive_summary.removed_articles_count}
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
                Collector & System Status
              </div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: '#0284c7', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <ShieldCheck size={20} color="#0284c7" />
                <span>{report.executive_summary.monitoring_status}</span>
              </div>
              <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '2px' }}>
                {report.monitoring_runs.status_summary}
              </div>
            </div>
          </div>

          {/* Two-Column Breakdown: Publisher Analytics & Section Distribution */}
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
                Publisher Distribution
              </h2>
              {report.publisher_breakdown.length === 0 ? (
                <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>No publisher activity recorded for this date.</p>
              ) : (
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
                Editorial Section Breakdown ({report.executive_summary.sections_count} Sections)
              </h2>
              {report.section_breakdown.length === 0 ? (
                <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>No section breakdown available.</p>
              ) : (
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
              )}
            </div>
          </div>

          {/* Lead Top Stories */}
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
              Lead Editorial Stories ({report.top_stories.length})
            </h2>
            {report.top_stories.length === 0 ? (
              <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13.5px' }}>
                No articles recorded for {report.executive_summary.reporting_date}.
              </div>
            ) : (
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
                        {story.published_at ? new Date(story.published_at).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', hour12: true }) + ' IST' : 'Recent'}
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
            )}
          </div>
        </>
      ) : null}
    </div>
  );
};
