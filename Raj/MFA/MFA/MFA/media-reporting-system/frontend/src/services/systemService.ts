import { ScraperStatusItem, SystemSettings } from '../types/dashboard';
import { mockScraperStatus, defaultSystemSettings } from '../data/mock/system';

let currentSettings = { ...defaultSystemSettings };

export const systemService = {
  async getScraperStatuses(): Promise<ScraperStatusItem[]> {
    return new Promise((resolve) => setTimeout(() => resolve([...mockScraperStatus]), 150));
  },

  async getSettings(): Promise<SystemSettings> {
    return new Promise((resolve) => setTimeout(() => resolve({ ...currentSettings }), 100));
  },

  async saveSettings(newSettings: Partial<SystemSettings>): Promise<SystemSettings> {
    return new Promise((resolve) => {
      currentSettings = { ...currentSettings, ...newSettings };
      setTimeout(() => resolve({ ...currentSettings }), 150);
    });
  },
};
