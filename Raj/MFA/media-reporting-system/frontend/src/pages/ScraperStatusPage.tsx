import React, { useState, useEffect } from 'react';
import { ScraperStatusItem } from '../types/dashboard';
import { systemService } from '../services/systemService';
import { StatusBadge } from '../components/common/StatusBadge';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import { Cpu, Clock, CheckCircle2, AlertTriangle, Play, RefreshCw } from 'lucide-react';

export const ScraperStatusPage: React.FC = () => {
  const [statuses, setStatuses] = useState<ScraperStatusItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activePoll, setActivePoll] = useState<string | null>(null);

  useEffect(() => {
    systemService.getScraperStatuses().then((res) => {
      setStatuses(res);
      setIsLoading(false);
    });
  }, []);

  const handleSimulateRun = (id: string) => {
    setActivePoll(id);
    setTimeout(() => {
      setActivePoll(null);
    }, 800);
  };

  if (isLoading) {
    return (
      <div style={{ padding: '24px 0' }}>
        <LoadingSkeleton rows={4} height={100} />
      </div>
    );
  }

  return (
    <div>
      {/* Simulation disclaimer banner */}
      <div
        style={{
          padding: '10px 16px',
          backgroundColor: '#fffbeb',
          border: '1px solid #fde68a',
          borderRadius: 'var(--radius-sm)',
          color: '#92400e',
          fontSize: '12.5px',
          marginBottom: '20px',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
        }}
      >
        <AlertTriangle size={14} flex-shrink="0" />
        <span>
          <strong>Phase 1 UI Mode:</strong> Scraper telemetry shown below represents simulated health metrics. Actual web scraping engines (Requests / BeautifulSoup / Playwright) and automated schedulers will be deployed in Phases 2, 3, and 7.
        </span>
      </div>

      {/* Header */}
      <div className="section-header" style={{ marginBottom: '20px' }}>
        <div>
          <h1 style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-main)' }}>
            Scraper Engine Telemetry
          </h1>
          <p style={{ fontSize: '13.5px', color: 'var(--text-muted)' }}>
            Status of background crawler instances, extraction throughput, and worker schedules
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span
            style={{
              fontSize: '12px',
              fontFamily: 'var(--font-mono)',
              padding: '4px 10px',
              backgroundColor: 'var(--bg-surface-subtle)',
              border: '1px solid var(--border-light)',
              borderRadius: 'var(--radius-xs)',
              color: 'var(--text-muted)',
            }}
          >
            Worker Pool: 2 Active
          </span>
        </div>
      </div>

      {/* Scraper Collector Cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
        {statuses.map((item) => {
          const isPolling = activePoll === item.id;
          return (
            <div
              key={item.id}
              style={{
                backgroundColor: '#ffffff',
                border: '1px solid var(--border-light)',
                borderRadius: 'var(--radius-md)',
                padding: '24px',
                boxShadow: 'var(--shadow-card)',
                display: 'flex',
                flexDirection: 'column',
                gap: '18px',
              }}
            >
              {/* Header */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                  <div
                    style={{
                      width: '42px',
                      height: '42px',
                      borderRadius: 'var(--radius-sm)',
                      backgroundColor: 'var(--bg-surface-subtle)',
                      border: '1px solid var(--border-light)',
                      color: 'var(--accent-primary)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <Cpu size={20} />
                  </div>
                  <div>
                    <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-main)' }}>
                      {item.name}
                    </h3>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                      Target: <span style={{ fontFamily: 'var(--font-mono)' }}>{item.url}</span>
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <StatusBadge status={item.status} />

                  <button
                    onClick={() => handleSimulateRun(item.id)}
                    disabled={isPolling}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '5px',
                      padding: '6px 14px',
                      backgroundColor: 'var(--accent-primary)',
                      color: '#ffffff',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: '12.5px',
                      fontWeight: 500,
                    }}
                  >
                    <Play size={12} />
                    <span>{isPolling ? 'Executing Run...' : 'Simulate Run'}</span>
                  </button>
                </div>
              </div>

              {/* Telemetry Metrics Grid */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(6, 1fr)',
                  backgroundColor: 'var(--bg-surface-subtle)',
                  border: '1px solid var(--border-light)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '14px',
                  gap: '10px',
                }}
              >
                <div>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Last Execution</span>
                  <div style={{ fontSize: '12.5px', fontWeight: 600, color: 'var(--text-main)', marginTop: '2px' }}>
                    {item.last_run.split('(')[0].trim()}
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Crawl Duration</span>
                  <div style={{ fontSize: '12.5px', fontWeight: 600, color: 'var(--text-main)', marginTop: '2px' }}>
                    {item.duration_sec}s
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Articles Parsed</span>
                  <div style={{ fontSize: '12.5px', fontWeight: 600, color: '#047857', marginTop: '2px' }}>
                    {item.articles_found} items
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Ad Units Detected</span>
                  <div style={{ fontSize: '12.5px', fontWeight: 600, color: '#0284c7', marginTop: '2px' }}>
                    {item.ads_found} units
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Error Count</span>
                  <div style={{ fontSize: '12.5px', fontWeight: 600, color: '#047857', marginTop: '2px' }}>
                    {item.errors_count} errors
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Next Scheduled Cycle</span>
                  <div style={{ fontSize: '12.5px', fontWeight: 600, color: 'var(--text-muted)', marginTop: '2px' }}>
                    {item.next_run.split('(')[0].trim()}
                  </div>
                </div>
              </div>

              {/* Extraction Framework Notice */}
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <CheckCircle2 size={13} color="var(--accent-primary)" />
                <span>Planned Framework: <strong>{item.mode}</strong> (Cadence: {item.frequency})</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
