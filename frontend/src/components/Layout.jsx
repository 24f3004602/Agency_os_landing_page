import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Users, Briefcase, FileText,
  Clock, CheckSquare, DollarSign, MessageSquare,
  TrendingDown, Megaphone, Search, UserCheck,
  Mail, Target, Zap, Layers, Settings,
  Bell, ChevronRight, LogOut, Menu, X,
  Building2, Activity, Lock
} from 'lucide-react'
import { clsx } from 'clsx'
import useAuthStore from '../store/authStore'

// Navigation config per role
const NAV = {
  superadmin: [
    { label: 'Overview',        icon: LayoutDashboard,  to: '/superadmin' },
    { label: 'Agencies',        icon: Building2,        to: '/superadmin/agencies' },
    { label: 'Module Control',  icon: Layers,           to: '/superadmin/modules' },
    { label: 'System Health',   icon: Activity,         to: '/superadmin/health' },
  ],
  owner: [
    { label: 'Home',            icon: LayoutDashboard,  to: '/owner' },
    { label: 'Team',            icon: Users,            to: '/owner/team' },
    { label: 'Clients',         icon: Briefcase,        to: '/owner/clients' },
    { label: 'Financial',       icon: DollarSign,       to: '/owner/financial' },
    { label: 'Reports',         icon: FileText,         to: '/owner/reports',     module: 'M3' },
    { label: 'Churn Alerts',    icon: TrendingDown,     to: '/owner/churn',       module: 'M4' },
    { label: 'Campaigns',       icon: Megaphone,        to: '/owner/campaigns',   module: 'M5' },
    { label: 'Research',        icon: Search,           to: '/owner/research',    module: 'M6' },
    { label: 'Leads',           icon: UserCheck,        to: '/owner/leads',       module: 'M7' },
    { label: 'Outreach',        icon: Mail,             to: '/owner/outreach',    module: 'M8' },
    { label: 'ABM',             icon: Target,           to: '/owner/abm',         module: 'M9' },
    { label: 'Optimisation',    icon: Zap,              to: '/owner/optimisation',module: 'M10' },
    { label: 'Content',         icon: Layers,           to: '/owner/content',     module: 'M11' },
    { label: 'AI Agents',       icon: Activity,         to: '/owner/agents' },
    { label: 'Communications',  icon: MessageSquare,    to: '/owner/communications' },
    { label: 'Settings',        icon: Settings,         to: '/owner/settings' },
  ],
  employee: [
    { label: 'My Day',          icon: LayoutDashboard,  to: '/employee' },
    { label: 'Attendance',      icon: Clock,            to: '/employee/attendance' },
    { label: 'My Tasks',        icon: CheckSquare,      to: '/employee/tasks' },
    { label: 'Campaign Tasks',  icon: Megaphone,        to: '/employee/campaign-tasks' },
    { label: 'Clients',         icon: Briefcase,        to: '/employee/clients' },
    { label: 'Payslips',        icon: DollarSign,       to: '/employee/payslips' },
  ],
  client: [
    { label: 'Campaigns',       icon: Megaphone,        to: '/client' },
    { label: 'Reports',         icon: FileText,         to: '/client/reports' },
    { label: 'Approvals',       icon: CheckSquare,      to: '/client/approvals' },
    { label: 'Messages',        icon: MessageSquare,    to: '/client/messages' },
    { label: 'Invoices',        icon: DollarSign,       to: '/client/invoices' },
  ],
}

const ROLE_COLORS = {
  superadmin: 'bg-gray-950 text-white',
  owner:      'bg-white border-r border-gray-200',
  employee:   'bg-white border-r border-gray-200',
  client:     'bg-white border-r border-gray-200',
}

const ROLE_LINK_ACTIVE = {
  superadmin: 'bg-white/10 text-white',
  owner:      'bg-brand-50 text-brand-600 font-semibold',
  employee:   'bg-brand-50 text-brand-600 font-semibold',
  client:     'bg-brand-50 text-brand-600 font-semibold',
}

const ROLE_LINK_DEFAULT = {
  superadmin: 'text-gray-400 hover:text-white hover:bg-white/5',
  owner:      'text-gray-600 hover:text-gray-900 hover:bg-gray-100',
  employee:   'text-gray-600 hover:text-gray-900 hover:bg-gray-100',
  client:     'text-gray-600 hover:text-gray-900 hover:bg-gray-100',
}

export default function Layout({ children }) {
  const { role, fullName, clearAuth, activeModules } = useAuthStore()
  const navigate = useNavigate()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [lockedModulePrompt, setLockedModulePrompt] = useState(null)

  const navItems = NAV[role] || []
  const sidebarColor = ROLE_COLORS[role] || ROLE_COLORS.owner

  const handleLogout = () => {
    clearAuth()
    navigate('/login', { replace: true })
  }

  const SidebarContent = () => (
    <div className={clsx('flex flex-col h-full', sidebarColor)}>
      {/* Brand */}
      <div className={clsx(
        'px-5 py-5 border-b',
        role === 'superadmin' ? 'border-white/10' : 'border-gray-200'
      )}>
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-brand-500 rounded-xl flex items-center justify-center flex-shrink-0">
            <span className="text-white text-sm font-bold">A</span>
          </div>
          <div className="min-w-0">
            <p className={clsx(
              'font-bold text-sm truncate',
              role === 'superadmin' ? 'text-white' : 'text-gray-900'
            )}>
              Agency OS
            </p>
            <p className={clsx(
              'text-xs truncate',
              role === 'superadmin' ? 'text-gray-400' : 'text-gray-500'
            )}>
              {role === 'superadmin' ? 'Super Admin' : fullName}
            </p>
          </div>
        </div>
      </div>

      {/* Nav links */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-0.5">
        {navItems.map(({ label, icon: Icon, to, module }) => {
          const isLocked = (
            role === 'owner' &&
            module &&
            !(activeModules || []).includes(module)
          )

          return (
          <NavLink
            key={to}
            to={to}
            end={to.split('/').length <= 2}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-colors',
                isLocked && 'opacity-70 hover:opacity-100',
                isActive
                  ? ROLE_LINK_ACTIVE[role]
                  : ROLE_LINK_DEFAULT[role]
              )
            }
            onClick={(e) => {
              if (isLocked) {
                e.preventDefault()
                setLockedModulePrompt({ label, module })
                return
              }
              setSidebarOpen(false)
            }}
          >
            <Icon size={17} />
            <span className="flex-1">{label}</span>
            {isLocked && (
              <Lock size={14} className="text-amber-500" />
            )}
          </NavLink>
          )
        })}
      </nav>

      {/* Logout */}
      <div className={clsx(
        'px-3 py-4 border-t',
        role === 'superadmin' ? 'border-white/10' : 'border-gray-200'
      )}>
        <button
          onClick={handleLogout}
          className={clsx(
            'flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm transition-colors',
            ROLE_LINK_DEFAULT[role]
          )}
        >
          <LogOut size={17} />
          Sign out
        </button>
      </div>
    </div>
  )

  return (
    <div className="flex h-screen overflow-hidden bg-surface-secondary">
      {/* Desktop sidebar */}
      <div className="hidden lg:flex lg:flex-shrink-0">
        <div className="w-60">
          <SidebarContent />
        </div>
      </div>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setSidebarOpen(false)}
          />
          <div className="absolute left-0 top-0 bottom-0 w-60 z-50">
            <SidebarContent />
          </div>
        </div>
      )}

      {lockedModulePrompt && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setLockedModulePrompt(null)}
          />
          <div className="relative w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
            <div className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-full bg-amber-100">
              <Lock size={18} className="text-amber-600" />
            </div>
            <h3 className="text-lg font-semibold text-gray-900">
              Module Locked
            </h3>
            <p className="mt-2 text-sm text-gray-600">
              You are not authorised to use the {lockedModulePrompt.label} module ({lockedModulePrompt.module}).
              Buy this module from Super Admin to unlock access.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                onClick={() => setLockedModulePrompt(null)}
              >
                Close
              </button>
              <button
                className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600"
                onClick={() => {
                  setLockedModulePrompt(null)
                  window.alert('Please contact Super Admin to buy and activate this module for your agency.')
                }}
              >
                Buy Module
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Topbar */}
        <div className="h-14 bg-white border-b border-gray-200 flex items-center px-4 gap-3 flex-shrink-0">
          <button
            onClick={() => setSidebarOpen(true)}
            className="lg:hidden p-2 rounded-lg hover:bg-gray-100"
          >
            <Menu size={18} />
          </button>
          <div className="flex-1" />
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-brand-500 rounded-full flex items-center justify-center">
              <span className="text-white text-xs font-semibold">
                {fullName?.charAt(0) || 'U'}
              </span>
            </div>
          </div>
        </div>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto">
          <div className="max-w-7xl mx-auto p-6">
            {children}
          </div>
        </main>
      </div>
    </div>
  )
}