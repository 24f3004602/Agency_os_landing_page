import { useQuery } from '@tanstack/react-query'
import { Clock, CheckSquare, DollarSign } from 'lucide-react'
import { PageHeader } from '../../components/ui/PageHeader'
import { StatCard } from '../../components/ui/card'
import { Badge } from '../../components/ui/Badge'
import { attendanceApi, taskApi, payrollApi } from '../../api/modules'

export default function EmployeeHome() {
  const { data: today } = useQuery({ queryKey: ['today-status'], queryFn: attendanceApi.today })
  const { data: tasks = [] } = useQuery({ queryKey: ['my-tasks'], queryFn: () => taskApi.myTasks() })
  const { data: payslips = [] } = useQuery({ queryKey: ['my-payslips'], queryFn: payrollApi.myPayslips })

  const pendingTasks = tasks.filter(t => ['created','in_progress'].includes(t.status))
  const submittedTasks = tasks.filter(t => t.status === 'submitted')

  return (
    <div>
      <PageHeader title="My Day" subtitle={new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })} />

      <div className="grid grid-cols-3 gap-4 mb-8">
        <div className={`card p-5 border-2 ${today?.is_clocked_in ? 'border-green-400' : 'border-gray-200'}`}>
          <div className="flex items-center gap-3">
            <div className={`p-2.5 rounded-xl ${today?.is_clocked_in ? 'bg-green-50 text-green-600' : 'bg-gray-100 text-gray-400'}`}>
              <Clock size={18} />
            </div>
            <div>
              <p className="text-sm text-gray-500">Attendance</p>
              <p className="font-bold text-gray-900">{today?.is_clocked_in ? 'Clocked In' : 'Not Clocked In'}</p>
            </div>
          </div>
        </div>
        <StatCard label="Pending Tasks" value={pendingTasks.length} icon={CheckSquare} color={pendingTasks.length > 0 ? 'amber' : 'green'} />
        <StatCard label="Submitted" value={submittedTasks.length} sub="awaiting review" icon={CheckSquare} color="blue" />
      </div>

      {/* Today's tasks */}
      <div className="card p-6">
        <h2 className="font-semibold text-gray-900 mb-4">Today's Tasks</h2>
        <div className="space-y-2">
          {tasks.filter(t => !['verified', 'rejected'].includes(t.status)).slice(0, 8).map(t => (
            <div key={t.id} className="flex items-center justify-between py-2.5 border-b border-gray-100 last:border-0">
              <div className="min-w-0 flex-1">
                <p className="font-medium text-sm text-gray-900 truncate">{t.title}</p>
                {t.deadline && (
                  <p className="text-xs text-gray-400">
                    Due: {new Date(t.deadline).toLocaleDateString('en-IN')}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-2 ml-3">
                <Badge status={t.priority} label={t.priority} />
                <Badge status={t.status} />
              </div>
            </div>
          ))}
          {tasks.length === 0 && (
            <p className="text-gray-400 text-sm text-center py-6">No tasks assigned yet</p>
          )}
        </div>
      </div>
    </div>
  )
}