import { useQuery } from '@tanstack/react-query'
import { FileText, CheckSquare, MessageSquare, DollarSign } from 'lucide-react'
import { PageHeader } from '../../components/ui/PageHeader'
import { StatCard } from '../../components/ui/card'
import { reportingApi, contentApi, operationsApi } from '../../api/modules'

export default function ClientHome() {
  const { data: reports = [] } = useQuery({ queryKey: ['client-reports'], queryFn: () => reportingApi.list() })
  const { data: approvals = [] } = useQuery({ queryKey: ['client-approvals'], queryFn: () => contentApi.listApprovals() })
  const { data: invoices = [] } = useQuery({ queryKey: ['client-invoices'], queryFn: () => operationsApi.listInvoices() })

  return (
    <div>
      <PageHeader title="Your Dashboard" subtitle="Campaign performance and updates" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard label="Reports" value={reports.length} icon={FileText} color="blue" />
        <StatCard label="Pending Approvals" value={approvals.length} icon={CheckSquare} color={approvals.length > 0 ? 'amber' : 'green'} />
        <StatCard label="Messages" value={0} icon={MessageSquare} color="purple" />
        <StatCard label="Invoices" value={invoices.length} icon={DollarSign} color="blue" />
      </div>
      {approvals.length > 0 && (
        <div className="card p-6">
          <h2 className="font-semibold text-gray-900 mb-4">⚡ Approvals Needed</h2>
          <div className="space-y-3">
            {approvals.map(a => (
              <div key={a.id} className="flex items-center justify-between p-3 bg-amber-50 border border-amber-200 rounded-xl">
                <div>
                  <p className="font-medium text-amber-900">{a.brief_title}</p>
                  <p className="text-xs text-amber-700">Angle: {a.draft_angle}</p>
                </div>
                <a href="/client/approvals" className="btn-primary text-sm">Review Now</a>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}