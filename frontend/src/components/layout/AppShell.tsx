import { NavLink, Navigate, Outlet } from 'react-router-dom';
import { useAuthStore } from '../../stores/authStore';
import { LogOut, BarChart3, LayoutDashboard, Scan, Package, Activity, FileText, Globe, Settings } from 'lucide-react';

const navItems = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/monitoring', label: 'Monitoring', icon: Scan },
  { to: '/software', label: 'Software', icon: Package },
  { to: '/signals', label: 'Signals', icon: Activity },
  { to: '/signals/reviews', label: 'Reviews', icon: FileText },
  { to: '/intelligence', label: 'Intelligence', icon: Globe },
  { to: '/settings', label: 'Settings', icon: Settings },
];

export function AppShell() {
  const { isAuthenticated, company, logout } = useAuthStore();

  if (!isAuthenticated) {
    return <Navigate to="/login" />;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-6 h-6 text-blue-600" />
            <span className="font-semibold text-lg text-gray-900">Vendor Intel</span>
          </div>
          <div className="flex items-center gap-1">
            {navItems.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/signals' || to === '/intelligence'}
                className={({ isActive }) =>
                  `flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium ${
                    isActive
                      ? 'bg-blue-50 text-blue-700'
                      : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                  }`
                }
              >
                <Icon className="w-4 h-4" />
                {label}
              </NavLink>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-600">{company?.company_name}</span>
          <button
            onClick={() => { logout(); window.location.href = '/login'; }}
            className="text-gray-500 hover:text-gray-700 cursor-pointer"
          >
            <LogOut className="w-5 h-5" />
          </button>
        </div>
      </nav>
      <main className="max-w-7xl mx-auto px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
