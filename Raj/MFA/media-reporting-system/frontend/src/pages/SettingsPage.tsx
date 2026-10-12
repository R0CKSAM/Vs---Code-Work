import React, { useState, useEffect } from 'react';
import { SystemSettings } from '../types/dashboard';
import { systemService } from '../services/systemService';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import { Settings as SettingsIcon, Bell, Globe, Sliders, Check } from 'lucide-react';

export const SettingsPage: React.FC = () => {
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [savedMsg, setSavedMsg] = useState(false);

  useEffect(() => {
    systemService.getSettings().then((res) => {
      setSettings(res);
      setIsLoading(false);
    });
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!settings) return;
    await systemService.saveSettings(settings);
    setSavedMsg(true);
    setTimeout(() => setSavedMsg(false), 3000);
  };

  if (isLoading || !settings) {
    return (
      <div style={{ padding: '24px 0' }}>
        <LoadingSkeleton rows={4} height={80} />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: '840px' }}>
      {/* Header */}
      <div className="section-header" style={{ marginBottom: '22px' }}>
        <div>
          <h1 style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-main)' }}>
            System Settings & Preferences
          </h1>
          <p style={{ fontSize: '13.5px', color: 'var(--text-muted)' }}>
            Configure local crawling parameters, notification webhooks, and dashboard defaults
          </p>
        </div>
      </div>

      {savedMsg && (
        <div
          style={{
            padding: '10px 16px',
            backgroundColor: '#ecfdf5',
            border: '1px solid #a7f3d0',
            borderRadius: 'var(--radius-sm)',
            color: '#065f46',
            fontSize: '13px',
            marginBottom: '18px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          <Check size={14} />
          <span>Local configuration updated successfully.</span>
        </div>
      )}

      <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {/* Section 1: Monitoring Engine Settings */}
        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--border-light)',
            borderRadius: 'var(--radius-md)',
            padding: '22px',
            boxShadow: 'var(--shadow-card)',
          }}
        >
          <h2 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Sliders size={16} color="var(--accent-primary)" />
            Monitoring Engine Parameters
          </h2>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div>
              <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', display: 'block' }}>
                Automated Monitoring Interval
              </label>
              <span style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
                How frequently background crawlers poll monitored publication homepages
              </span>
              <select
                value={settings.monitoring_interval_minutes}
                onChange={(e) =>
                  setSettings({ ...settings, monitoring_interval_minutes: Number(e.target.value) })
                }
                className="filter-select"
                style={{ width: '260px' }}
              >
                <option value={5}>Every 5 minutes</option>
                <option value={10}>Every 10 minutes (Standard)</option>
                <option value={15}>Every 15 minutes</option>
                <option value={30}>Every 30 minutes</option>
                <option value={60}>Every 1 hour</option>
              </select>
            </div>

            <div>
              <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', display: 'block' }}>
                Crawler Concurrency Level
              </label>
              <span style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
                Maximum concurrent HTTP / browser worker threads executed simultaneously
              </span>
              <select
                value={settings.crawler_concurrency}
                onChange={(e) =>
                  setSettings({ ...settings, crawler_concurrency: Number(e.target.value) })
                }
                className="filter-select"
                style={{ width: '260px' }}
              >
                <option value={1}>1 Worker (Sequential)</option>
                <option value={2}>2 Workers (Parallel)</option>
                <option value={4}>4 Workers (High Throughput)</option>
              </select>
            </div>
          </div>
        </div>

        {/* Section 2: Dashboard Defaults */}
        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--border-light)',
            borderRadius: 'var(--radius-md)',
            padding: '22px',
            boxShadow: 'var(--shadow-card)',
          }}
        >
          <h2 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Globe size={16} color="var(--accent-primary)" />
            Dashboard Defaults & Filters
          </h2>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <div>
              <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', display: 'block', marginBottom: '4px' }}>
                Default Target Website
              </label>
              <select
                value={settings.default_website}
                onChange={(e) => setSettings({ ...settings, default_website: e.target.value })}
                className="filter-select"
                style={{ width: '100%' }}
              >
                <option value="all">All Websites (Aggregated)</option>
                <option value="et-brandequity">ET BrandEquity Only</option>
                <option value="exchange4media">Exchange4media Only</option>
              </select>
            </div>

            <div>
              <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', display: 'block', marginBottom: '4px' }}>
                Default Date Scope
              </label>
              <select
                value={settings.default_date_range}
                onChange={(e) => setSettings({ ...settings, default_date_range: e.target.value })}
                className="filter-select"
                style={{ width: '100%' }}
              >
                <option value="today">Today (Real-time)</option>
                <option value="last-24h">Last 24 Hours</option>
                <option value="last-7-days">Last 7 Days</option>
              </select>
            </div>
          </div>
        </div>

        {/* Section 3: Alerts & Notifications */}
        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--border-light)',
            borderRadius: 'var(--radius-md)',
            padding: '22px',
            boxShadow: 'var(--shadow-card)',
          }}
        >
          <h2 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-main)', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Bell size={16} color="var(--accent-primary)" />
            Notifications & Intelligence Alerts
          </h2>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={settings.enable_notifications}
                onChange={(e) =>
                  setSettings({ ...settings, enable_notifications: e.target.checked })
                }
                style={{ width: '16px', height: '16px' }}
              />
              <div>
                <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)' }}>
                  Enable In-App Breaking Change Alerts
                </span>
                <span style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'block' }}>
                  Show badge notifications when high-impact ad removals or headline changes are recorded
                </span>
              </div>
            </label>

            <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={settings.enable_sound_alerts}
                onChange={(e) =>
                  setSettings({ ...settings, enable_sound_alerts: e.target.checked })
                }
                style={{ width: '16px', height: '16px' }}
              />
              <div>
                <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)' }}>
                  Audio Chime on Critical Discrepancies
                </span>
                <span style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'block' }}>
                  Play a subtle tone when crawler detects 5xx server downtime on tracked websites
                </span>
              </div>
            </label>
          </div>
        </div>

        {/* Submit */}
        <div>
          <button
            type="submit"
            style={{
              padding: '10px 20px',
              backgroundColor: 'var(--accent-primary)',
              color: '#ffffff',
              borderRadius: 'var(--radius-sm)',
              fontSize: '13px',
              fontWeight: 600,
            }}
          >
            Save Preferences
          </button>
        </div>
      </form>
    </div>
  );
};
