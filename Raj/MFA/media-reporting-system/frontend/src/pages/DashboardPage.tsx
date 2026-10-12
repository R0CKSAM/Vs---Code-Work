import React, { useState } from 'react';
import { DashboardResponse, NewsArticle } from '../types/dashboard';
import { Header } from '../components/dashboard/Header';
import { KPICards } from '../components/dashboard/KPICards';
import { WebsiteSection } from '../components/dashboard/WebsiteSection';
import { FilterBar } from '../components/dashboard/FilterBar';
import { LatestNewsSection } from '../components/dashboard/LatestNewsSection';
import { NewsDetailDrawer } from '../components/news/NewsDetailDrawer';

interface DashboardPageProps {
  data: DashboardResponse;
  isLive: boolean;
  searchQuery: string;
  onRefresh: () => void;
  isRefreshing: boolean;
  onSelectWebsite?: (id: string) => void;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({
  data,
  isLive,
  searchQuery,
  onRefresh,
  isRefreshing,
  onSelectWebsite,
}) => {
  const [selectedWebsite, setSelectedWebsite] = useState('all');
  const [selectedSection, setSelectedSection] = useState('all');
  const [selectedDate, setSelectedDate] = useState('today');
  const [selectedContentType, setSelectedContentType] = useState('all');

  // Detail drawer for articles
  const [selectedArticle, setSelectedArticle] = useState<NewsArticle | null>(null);

  const handleResetFilters = () => {
    setSelectedWebsite('all');
    setSelectedSection('all');
    setSelectedDate('today');
    setSelectedContentType('all');
  };

  return (
    <div>
      {/* 1. Header */}
      <Header
        systemStatus={data.system_status}
        isLive={isLive}
        onRefresh={onRefresh}
        isRefreshing={isRefreshing}
      />

      {/* 2. Primary KPI Cards & Intelligence Metrics Row */}
      <KPICards kpis={data.kpis} />

      {/* 3. Website Monitoring Section */}
      <WebsiteSection websites={data.websites} onSelectWebsite={onSelectWebsite} />

      {/* 4. Filter Bar */}
      <FilterBar
        selectedWebsite={selectedWebsite}
        onSelectWebsite={setSelectedWebsite}
        selectedSection={selectedSection}
        onSelectSection={setSelectedSection}
        selectedDate={selectedDate}
        onSelectDate={setSelectedDate}
        selectedContentType={selectedContentType}
        onSelectContentType={setSelectedContentType}
        onReset={handleResetFilters}
      />

      {/* 5. Latest News Section */}
      <LatestNewsSection
        articles={data.latest_news}
        selectedWebsite={selectedWebsite}
        selectedSection={selectedSection}
        searchQuery={searchQuery}
      />

      {/* Article Detail Drawer */}
      <NewsDetailDrawer
        article={selectedArticle}
        isOpen={Boolean(selectedArticle)}
        onClose={() => setSelectedArticle(null)}
      />
    </div>
  );
};
