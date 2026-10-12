# Media Reporting System - Frontend

React + TypeScript + Vite dashboard for the Media Reporting System.

## Architecture (Phase 0)

In **Phase 0 — Foundation**, the frontend features:
- **Design Aesthetic**: Minimal, modern, corporate media intelligence platform (slate/zinc palette, clear typography, desktop-first responsive layout).
- **Component Layering**:
  - `components/dashboard/`: Header, KPICards, WebsiteSection, LatestNewsSection, FilterBar, SearchBar
  - `layouts/`: Sidebar with multi-tier navigation, Topbar with live API connection indicator and search
  - `pages/`: DashboardPage and Phase Roadmap PlaceholderPage
  - `api/`: Strongly-typed API client connecting to FastAPI `GET /api/dashboard` with offline fallback
- **Navigation**:
  - Overview: Dashboard
  - Monitoring: Websites, News, Advertisements, Changes
  - Reports: Daily Report, Weekly Report, Custom Report
  - System: Scraper Status, Settings

---

## Directory Structure

```
frontend/
├── index.html
├── package.json
├── tsconfig.json
├── tsconfig.node.json
├── vite.config.ts
├── src/
│   ├── api/
│   │   ├── client.ts         # Fetch API client configured with base URL
│   │   └── dashboard.ts      # Dashboard & Health endpoints
│   ├── components/
│   │   ├── common/           # Reusable UI primitives (Badge, Card)
│   │   └── dashboard/        # Dashboard layout widgets
│   ├── data/
│   │   └── mockFallback.ts   # Client-side fallback data
│   ├── layouts/
│   │   ├── MainLayout.tsx
│   │   ├── Sidebar.tsx
│   │   └── Topbar.tsx
│   ├── pages/
│   │   ├── DashboardPage.tsx
│   │   └── PlaceholderPage.tsx
│   ├── styles/
│   │   └── index.css         # Corporate design system styling
│   ├── types/
│   │   └── dashboard.ts      # TypeScript interfaces matching backend schemas
│   ├── App.tsx
│   └── main.tsx
└── README.md
```

---

## How to Run

### 1. Prerequisites
- Node.js 18+ and npm installed

### 2. Install Dependencies
```bash
cd frontend
npm install
```

### 3. Run Development Server
```bash
npm run dev
```

The frontend will run at:
- `http://127.0.0.1:5173` or `http://localhost:5173`

It automatically detects the backend running at `http://127.0.0.1:8000/api`. If the backend is not running, it automatically operates in graceful offline mock mode with a visual indicator.
