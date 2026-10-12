/**
 * Reporting API Client
 * Interfaces with FastAPI endpoints at /api/reports/*
 */
import { apiFetch, API_BASE_URL } from './client';
import {
  DailyReportResponse,
  WeeklyReportResponse,
  CustomReportResponse,
  CustomReportParams,
  ExportReportParams,
} from '../types/reports';

/**
 * Fetches the daily media intelligence brief for a specified calendar date
 */
export async function fetchDailyReport(date?: string): Promise<DailyReportResponse> {
  const query = date ? `?date=${encodeURIComponent(date)}` : '';
  return apiFetch<DailyReportResponse>(`/reports/daily${query}`);
}

/**
 * Fetches the weekly industry roll-up report for a date range
 */
export async function fetchWeeklyReport(
  startDate?: string,
  endDate?: string
): Promise<WeeklyReportResponse> {
  const params = new URLSearchParams();
  if (startDate) params.append('start_date', startDate);
  if (endDate) params.append('end_date', endDate);
  const query = params.toString() ? `?${params.toString()}` : '';
  return apiFetch<WeeklyReportResponse>(`/reports/weekly${query}`);
}

/**
 * Fetches custom multi-criteria dossier
 */
export async function fetchCustomReport(
  params: CustomReportParams
): Promise<CustomReportResponse> {
  const queryParams = new URLSearchParams();
  if (params.start_date) queryParams.append('start_date', params.start_date);
  if (params.end_date) queryParams.append('end_date', params.end_date);
  if (params.website && params.website !== 'all') queryParams.append('website', params.website);
  if (params.section && params.section !== 'all') queryParams.append('section', params.section);
  if (params.status && params.status !== 'ALL') queryParams.append('status', params.status);
  if (params.search && params.search.trim()) queryParams.append('search', params.search.trim());
  if (params.limit) queryParams.append('limit', String(params.limit));

  const query = queryParams.toString() ? `?${queryParams.toString()}` : '';
  return apiFetch<CustomReportResponse>(`/reports/custom${query}`);
}

/**
 * Downloads a real compiled PDF, Excel, or CSV report from /api/reports/export
 */
export async function downloadReportExport(params: ExportReportParams): Promise<void> {
  const queryParams = new URLSearchParams();
  queryParams.append('report_type', params.report_type);
  queryParams.append('format', params.format);

  if (params.date) queryParams.append('date', params.date);
  if (params.start_date) queryParams.append('start_date', params.start_date);
  if (params.end_date) queryParams.append('end_date', params.end_date);
  if (params.website && params.website !== 'all') queryParams.append('website', params.website);
  if (params.section && params.section !== 'all') queryParams.append('section', params.section);
  if (params.status && params.status !== 'ALL') queryParams.append('status', params.status);
  if (params.search && params.search.trim()) queryParams.append('search', params.search.trim());

  const url = `${API_BASE_URL}/reports/export?${queryParams.toString()}`;
  const response = await fetch(url);

  if (!response.ok) {
    let errorDetail = response.statusText;
    try {
      const errJson = await response.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch {
      // Use status text fallback
    }
    throw new Error(`Export download failed (${response.status}): ${errorDetail}`);
  }

  const blob = await response.blob();
  const disposition = response.headers.get('content-disposition');
  let filename = `${params.report_type}_report.${params.format === 'excel' ? 'xlsx' : params.format}`;
  if (disposition && disposition.includes('filename=')) {
    const match = disposition.match(/filename="?([^"]+)"?/);
    if (match && match[1]) {
      filename = match[1];
    }
  }

  const blobUrl = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = blobUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(blobUrl);
}
