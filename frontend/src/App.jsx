import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import ProtectedRoute from './components/ProtectedRoute'
import Layout from './components/Layout'
import Login from './pages/Login'
import useAuthStore from './store/authStore'

// SuperAdmin pages
import SuperAdminHome from './pages/superadmin/Home'
import SuperAdminAgencies from './pages/superadmin/Agencies'
import SuperAdminModules from './pages/superadmin/Modules'

// Owner pages
import OwnerHome from './pages/owner/Home'
import OwnerTeam from './pages/owner/Team'
import OwnerClients from './pages/owner/Clients'
import OwnerFinancial from './pages/owner/Financial'
import OwnerReports from './pages/owner/Reports'
import OwnerChurn from './pages/owner/Churn'
import OwnerCampaigns from './pages/owner/Campaigns'
import OwnerResearch from './pages/owner/Research'
import OwnerLeads from './pages/owner/Leads'
import OwnerOutreach from './pages/owner/Outreach'
import OwnerAbm from './pages/owner/Abm'
import OwnerOptimisation from './pages/owner/Optimisation'
import OwnerContent from './pages/owner/Content'
import OwnerCommunications from './pages/owner/Communications'

// Employee pages
import EmployeeHome from './pages/employee/Home'
import EmployeeAttendance from './pages/employee/Attendance'
import EmployeeTasks from './pages/employee/Tasks'
import EmployeeCampaignTasks from './pages/employee/CampaignTasks'
import EmployeePayslips from './pages/employee/Payslips'
import EmployeeClients from './pages/employee/Clients'

// Client pages
import ClientHome from './pages/client/Home'
import ClientReports from './pages/client/Reports'
import ClientApprovals from './pages/client/Approvals'
import ClientMessages from './pages/client/Messages'
import ClientInvoices from './pages/client/Invoices'

function RootRedirect() {
  const { accessToken, role } = useAuthStore()
  if (!accessToken) return <Navigate to="/login" replace />
  const map = { superadmin: '/superadmin', owner: '/owner', employee: '/employee', client: '/client' }
  return <Navigate to={map[role] ?? '/login'} replace />
}

function DashboardLayout({ children, roles, requiredModule }) {
  return (
    <ProtectedRoute roles={roles} requiredModule={requiredModule}>
      <Layout>{children}</Layout>
    </ProtectedRoute>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<RootRedirect />} />

        {/* SuperAdmin */}
        <Route path="/superadmin" element={<DashboardLayout roles={['superadmin']}><SuperAdminHome /></DashboardLayout>} />
        <Route path="/superadmin/agencies" element={<DashboardLayout roles={['superadmin']}><SuperAdminAgencies /></DashboardLayout>} />
        <Route path="/superadmin/modules" element={<DashboardLayout roles={['superadmin']}><SuperAdminModules /></DashboardLayout>} />

        {/* Owner */}
        <Route path="/owner" element={<DashboardLayout roles={['owner','superadmin']}><OwnerHome /></DashboardLayout>} />
        <Route path="/owner/team" element={<DashboardLayout roles={['owner','superadmin']}><OwnerTeam /></DashboardLayout>} />
        <Route path="/owner/clients" element={<DashboardLayout roles={['owner','superadmin']}><OwnerClients /></DashboardLayout>} />
        <Route path="/owner/financial" element={<DashboardLayout roles={['owner','superadmin']}><OwnerFinancial /></DashboardLayout>} />
        <Route path="/owner/reports" element={<DashboardLayout roles={['owner','superadmin']} requiredModule="M3"><OwnerReports /></DashboardLayout>} />
        <Route path="/owner/churn" element={<DashboardLayout roles={['owner','superadmin']} requiredModule="M4"><OwnerChurn /></DashboardLayout>} />
        <Route path="/owner/campaigns" element={<DashboardLayout roles={['owner','superadmin']} requiredModule="M5"><OwnerCampaigns /></DashboardLayout>} />
        <Route path="/owner/research" element={<DashboardLayout roles={['owner','superadmin']} requiredModule="M6"><OwnerResearch /></DashboardLayout>} />
        <Route path="/owner/leads" element={<DashboardLayout roles={['owner','superadmin']} requiredModule="M7"><OwnerLeads /></DashboardLayout>} />
        <Route path="/owner/outreach" element={<DashboardLayout roles={['owner','superadmin']} requiredModule="M8"><OwnerOutreach /></DashboardLayout>} />
        <Route path="/owner/abm" element={<DashboardLayout roles={['owner','superadmin']} requiredModule="M9"><OwnerAbm /></DashboardLayout>} />
        <Route path="/owner/optimisation" element={<DashboardLayout roles={['owner','superadmin']} requiredModule="M10"><OwnerOptimisation /></DashboardLayout>} />
        <Route path="/owner/content" element={<DashboardLayout roles={['owner','superadmin']} requiredModule="M11"><OwnerContent /></DashboardLayout>} />
        <Route path="/owner/communications" element={<DashboardLayout roles={['owner','superadmin']}><OwnerCommunications /></DashboardLayout>} />

        {/* Employee */}
        <Route path="/employee" element={<DashboardLayout roles={['employee']}><EmployeeHome /></DashboardLayout>} />
        <Route path="/employee/attendance" element={<DashboardLayout roles={['employee']}><EmployeeAttendance /></DashboardLayout>} />
        <Route path="/employee/tasks" element={<DashboardLayout roles={['employee']}><EmployeeTasks /></DashboardLayout>} />
        <Route path="/employee/campaign-tasks" element={<DashboardLayout roles={['employee']}><EmployeeCampaignTasks /></DashboardLayout>} />
        <Route path="/employee/payslips" element={<DashboardLayout roles={['employee']}><EmployeePayslips /></DashboardLayout>} />
        <Route path="/employee/clients" element={<DashboardLayout roles={['employee']}><EmployeeClients /></DashboardLayout>} />

        {/* Client */}
        <Route path="/client" element={<DashboardLayout roles={['client']}><ClientHome /></DashboardLayout>} />
        <Route path="/client/reports" element={<DashboardLayout roles={['client']}><ClientReports /></DashboardLayout>} />
        <Route path="/client/approvals" element={<DashboardLayout roles={['client']}><ClientApprovals /></DashboardLayout>} />
        <Route path="/client/messages" element={<DashboardLayout roles={['client']}><ClientMessages /></DashboardLayout>} />
        <Route path="/client/invoices" element={<DashboardLayout roles={['client']}><ClientInvoices /></DashboardLayout>} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}