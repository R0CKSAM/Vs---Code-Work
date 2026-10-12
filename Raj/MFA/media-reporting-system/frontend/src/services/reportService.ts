/**
 * Report Service
 * Centralizes reporting API operations with graceful offline handling and live execution.
 */
import {
  fetchDailyReport,
  fetchWeeklyReport,
  fetchCustomReport,
  downloadReportExport,
} from '../api/reports';
import {
  DailyReportResponse,
  WeeklyReportResponse,
  CustomReportResponse,
  CustomReportParams,
  ExportReportParams,
} from '../types/reports';

export const reportService = {
  /**
   * Generates Daily Executive Intelligence Brief
   */
  async getDailyReport(date?: string): Promise<DailyReportResponse> {
    return fetchDailyReport(date);
  },

  /**
   * Generates Weekly Industry Roll-up Report
   */
  async getWeeklyReport(startDate?: string, endDate?: string): Promise<WeeklyReportResponse> {
    return fetchWeeklyReport(startDate, endDate);
  },

  /**
   * Generates Parametric Custom Dossier Report
   */
  async getCustomReport(params: CustomReportParams): Promise<CustomReportResponse> {
    return fetchCustomReport(params);
  },

  /**
   * Triggers professional file export download (PDF, Excel, CSV)
   */
  async exportReport(params: ExportReportParams): Promise<void> {
    return downloadReportExport(params);
  },
};
