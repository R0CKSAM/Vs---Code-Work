import React, { useState, useEffect } from 'react';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';
import { CommandPalette } from '../components/common/CommandPalette';
import { NavRoute } from '../types/dashboard';

interface MainLayoutProps {
  currentRoute: NavRoute;
  onNavigate: (route: NavRoute) => void;
  isLive: boolean;
  onRefreshData?: () => void;
  isRefreshing?: boolean;
  onSelectArticleFromSearch: (id: string) => void;
  onSelectAdFromSearch: (id: string) => void;
  onSelectWebsiteFromSearch: (id: string) => void;
  children: React.ReactNode;
}

export const MainLayout: React.FC<MainLayoutProps> = ({
  currentRoute,
  onNavigate,
  isLive,
  onRefreshData,
  isRefreshing = false,
  onSelectArticleFromSearch,
  onSelectAdFromSearch,
  onSelectWebsiteFromSearch,
  children,
}) => {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isPaletteOpen, setIsPaletteOpen] = useState(false);

  // Global keyboard shortcut Ctrl+K or ⌘K
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setIsPaletteOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  return (
    <div className="app-container">
      <Sidebar
        currentRoute={currentRoute}
        onNavigate={onNavigate}
        isCollapsed={isCollapsed}
        onToggleCollapse={() => setIsCollapsed(!isCollapsed)}
      />

      <div className="main-wrapper">
        <Topbar
          currentRoute={currentRoute}
          isLive={isLive}
          onOpenCommandPalette={() => setIsPaletteOpen(true)}
          onRefreshData={onRefreshData}
          isRefreshing={isRefreshing}
        />

        <main className="content-area">{children}</main>
      </div>

      {/* Global Command Palette */}
      <CommandPalette
        isOpen={isPaletteOpen}
        onClose={() => setIsPaletteOpen(false)}
        onSelectArticle={onSelectArticleFromSearch}
        onSelectAd={onSelectAdFromSearch}
        onSelectWebsite={onSelectWebsiteFromSearch}
      />
    </div>
  );
};
