import { useQuery } from '@tanstack/react-query'
import { Users, Briefcase, CheckSquare, TrendingDown, DollarSign, AlertCircle } from 'lucide-react'
import { PageHeader } from '../../components/ui/PageHeader'
import { StatCard } from '../../components/ui/card'
import { Badge } from '../../components/ui/Badge'
import { clientApi, taskApi, attendanceApi, churnApi } from '../../api/modules'

export default function OwnerHome() {
  const { data: clients = [] } = useQuery({ queryKey: ['clients'], queryFn: () => clientApi.list() })
  const { data: tasks = [] } = useQuery({ queryKey: ['tasks'], queryFn: () => taskApi.list() })
  const { data: team = [] } = useQuery({ queryKey: ['team-today'], queryFn: () => attendanceApi.team({ date_filter: new Date().toISOString().split('T')[0] }) })
  const { data: alerts = [] } = useQuery({ queryKey: ['churn-alerts'], queryFn: () => churnApi.listAlerts(), })

  const clockedInNow = team.filter(e => e.sessions?.some(s => s.status === 'open')).length
  const atRisk = clients.filter(c => c.status === 'at_risk').length
  const overdueTasks = tasks.filter(t => t.status === 'overdue').length
  const openAlerts = alerts.length

  return (
    <div>
      <PageHeader title="Agency Overview" subtitle={`Today — ${new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' })}`} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard label="Active Clients" value={clients.filter(c => c.status === 'active').length} icon={Briefcase} color="blue" />
        <StatCard label="Clocked In Now" value={clockedInNow} sub={`of ${team.length} employees`} icon={Users} color="green" />
        <StatCard label="Overdue Tasks" value={overdueTasks} icon={CheckSquare} color={overdueTasks > 0 ? 'red' : 'green'} />
        <StatCard label="Churn Alerts" value={openAlerts} icon={TrendingDown} color={openAlerts > 0 ? 'amber' : 'green'} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* At-risk clients */}
        <div className="card p-6">
          <h2 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <AlertCircle size={16} className="text-amber-500" />
            At-Risk Clients
          </h2>
          {atRisk === 0 ? (
            <p className="text-gray-400 text-sm text-center py-6">All clients are healthy ✓</p>
          ) : (
            <div className="space-y-2">
              {clients.filter(c => c.status === 'at_risk').map(c => (
                <div key={c.id} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
                  <p className="font-medium text-sm">{c.company_name}</p>
                  <Badge status="at_risk" />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Recent tasks */}
        <div className="card p-6">
          <h2 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <CheckSquare size={16} className="text-brand-500" />
            Recent Tasks
          </h2>
          <div className="space-y-2">
            {tasks.slice(0, 6).map(t => (
              <div key={t.id} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
                <p className="text-sm font-medium text-gray-800 truncate flex-1 mr-3">{t.title}</p>
                <Badge status={t.status} />
              </div>
            ))}
            {tasks.length === 0 && (
              <p className="text-gray-400 text-sm text-center py-6">No tasks yet</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}