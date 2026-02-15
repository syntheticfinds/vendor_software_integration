import { createBrowserRouter, Navigate } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { LoginPage } from './features/auth/LoginPage';
import { RegisterPage } from './features/auth/RegisterPage';
import { DashboardPage } from './features/dashboard/DashboardPage';
import { DetectionsListPage } from './features/monitoring/DetectionsListPage';
import { SoftwareListPage } from './features/software/SoftwareListPage';
import { SignalFeedPage } from './features/signals/SignalFeedPage';
import { ReviewDraftsPage } from './features/signals/ReviewDraftsPage';
import { PublicIndexPage } from './features/portal/PublicIndexPage';
import { ChatPage } from './features/portal/ChatPage';
import { OutreachPage } from './features/outreach/OutreachPage';
import { IntelligenceIndexPage } from './features/intelligence/IntelligenceIndexPage';
import { SolutionDetailPage } from './features/intelligence/SolutionDetailPage';
import { CUJDrilldownPage } from './features/intelligence/CUJDrilldownPage';
import { DemoControlPanel } from './features/demo/DemoControlPanel';
import { SettingsPage } from './features/settings/SettingsPage';

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  { path: '/register', element: <RegisterPage /> },
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/dashboard" /> },
      { path: 'dashboard', element: <DashboardPage /> },
      { path: 'monitoring', element: <DetectionsListPage /> },
      { path: 'software', element: <SoftwareListPage /> },
      { path: 'signals', element: <SignalFeedPage /> },
      { path: 'signals/reviews', element: <ReviewDraftsPage /> },
      { path: 'outreach', element: <OutreachPage /> },
      { path: 'intelligence', element: <IntelligenceIndexPage /> },
      { path: 'intelligence/:vendor/:software', element: <SolutionDetailPage /> },
      { path: 'intelligence/:vendor/:software/drilldown/:stage', element: <CUJDrilldownPage /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
  { path: '/demo', element: <DemoControlPanel /> },
  { path: '/portal', element: <PublicIndexPage /> },
  { path: '/portal/chat', element: <ChatPage /> },
]);
