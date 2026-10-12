import { ContentChange } from '../types/dashboard';
import { mockChanges } from '../data/mock/changes';

export const changeService = {
  async getAllChanges(): Promise<ContentChange[]> {
    return new Promise((resolve) => setTimeout(() => resolve([...mockChanges]), 150));
  },

  async getChangesByWebsite(websiteId: string): Promise<ContentChange[]> {
    return new Promise((resolve) => {
      const filtered = mockChanges.filter((c) => c.website_id === websiteId);
      setTimeout(() => resolve(filtered), 150);
    });
  },
};
