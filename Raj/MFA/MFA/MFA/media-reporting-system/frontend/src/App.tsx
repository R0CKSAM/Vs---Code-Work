import React, { useState, useEffect, useCallback } from 'react';
import { MainLayout } from './layouts/MainLayout';
import { DashboardPage } from './pages/DashboardPage';
import { WebsitesPage } from './pages/WebsitesPage';
import { WebsiteDetailPage } from './pages/WebsiteDetailPage';
import { NewsPage } from './pages/NewsPage';
import { AdvertisementsPage } from './pages/AdvertisementsPage';
import { ChangesPage } from './pages/ChangesPage';
import { DailyReportPage } from './pages/DailyReportPage';
import { WeeklyReportPage } from './pages/WeeklyReportPage';
import { CustomReportPage } from './pages/CustomReportPage';
import { ScraperStatusPage } from './pages/ScraperStatusPage';
import { SettingsPage } from './pages/SettingsPage';
import { dashboardService } from './services/dashboardService';
import { DashboardResponse, NavRoute } from './types/dashboard';
import { emptyDashboard } from './data/emptyDashboard';

export const App: React.FC = () => {
  const [currentRoute, setCurrentRoute] = useState<NavRoute>('dashboard');
  const [activeWebsiteId, setActiveWebsiteId] = useState<string>('et-brandequity');
  const [activeArticleId, setActiveArticleId] = useState<string | null>(null);
  const [activeAdId, setActiveAdId] = useState<string | null>(null);

  const [dashboardData, setDashboardData] = useState<DashboardResponse>(emptyDashboard);
  const [isLive, setIsLive] = useState<boolean>(false);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);

  // Load dashboard overview metrics
  const loadData = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const res = await dashboardService.getDashboard();
      setDashboardData(res.data);
      setIsLive(res.isLive);
    } catch {
      setIsLive(false);
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  // Handlers for selection & routing
  const handleSelectWebsiteDetail = (websiteId: string) => {
    setActiveWebsiteId(websiteId);
    setCurrentRoute('monitoring/websites/:websiteId');
  };

  const handleSelectArticleFromSearch = (articleId: string) => {
    setActiveArticleId(articleId);
    setCurrentRoute('monitoring/news');
  };

  const handleSelectAdFromSearch = (adId: string) => {
    setActiveAdId(adId);
    setCurrentRoute('monitoring/advertisements');
  };

  const handleSelectWebsiteFromSearch = (websiteId: string) => {
    setActiveWebsiteId(websiteId);
    setCurrentRoute('monitoring/websites/:websiteId');
  };

  const renderContent = () => {
    switch (currentRoute) {
      case 'dashboard':
        return (
          <DashboardPage
            data={dashboardData}
            isLive={isLive}
            searchQuery=""
            onRefresh={loadData}
            isRefreshing={isRefreshing}
            onSelectWebsite={handleSelectWebsiteDetail}
          />
        );
      case 'monitoring/websites':
        return <WebsitesPage onSelectWebsiteDetail={handleSelectWebsiteDetail} />;
      case 'monitoring/websites/:websiteId':
        return (
          <WebsiteDetailPage
            websiteId={activeWebsiteId}
            onBack={() => setCurrentRoute('monitoring/websites')}
          />
        );
      case 'monitoring/news':
        return <NewsPage initialArticleId={activeArticleId} />;
      case 'monitoring/advertisements':
        return <AdvertisementsPage initialAdId={activeAdId} />;
      case 'monitoring/changes':
        return <ChangesPage />;
      case 'reports/daily':
        return <DailyReportPage />;
      case 'reports/weekly':
        return <WeeklyReportPage />;
      case 'reports/custom':
        return <CustomReportPage />;
      case 'system/scraper-status':
        return <ScraperStatusPage />;
      case 'system/settings':
        return <SettingsPage />;
      default:
        return (
          <DashboardPage
            data={dashboardData}
            isLive={isLive}
            searchQuery=""
            onRefresh={loadData}
            isRefreshing={isRefreshing}
            onSelectWebsite={handleSelectWebsiteDetail}
          />
        );
    }
  };

  return (
    <MainLayout
      currentRoute={currentRoute}
      onNavigate={(route) => {
        setActiveArticleId(null);
        setActiveAdId(null);
        setCurrentRoute(route);
      }}
      isLive={isLive}
      onRefreshData={loadData}
      isRefreshing={isRefreshing}
      onSelectArticleFromSearch={handleSelectArticleFromSearch}
      onSelectAdFromSearch={handleSelectAdFromSearch}
      onSelectWebsiteFromSearch={handleSelectWebsiteFromSearch}
    >
      {renderContent()}
    </MainLayout>
  );
};

export default App;
