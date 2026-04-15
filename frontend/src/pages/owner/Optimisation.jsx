import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Zap, AlertTriangle } from 'lucide-react'
import { PageHeader } from '../../components/ui/PageHeader'
import { Badge } from '../../components/ui/Badge'
import { optimisationApi, clientApi } from '../../api/modules'

export default function OwnerOptimisation() {
  const [tab, setTab] = useState('runs')
  const [selectedClient, setSelectedClient] = useState('')
  const qc = useQueryClient()

  const { data: runs = [] } = useQuery({ queryKey: ['opt-runs'], queryFn: () => optimisationApi.listRuns() })
  const { data: alerts = [] } = useQuery({ queryKey: ['traj-alerts'], queryFn: () => optimisationApi.listAlerts() })
  const { data: clients = [] } = useQuery({ queryKey: ['clients'], queryFn: () => clientApi.list() })

  const trigger = useMutation({
    mutationFn: (clientId) => optimisationApi.triggerRun(clientId),
    onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ['opt-runs'] }), 25000),
  })

  const acknowledge = useMutation({
    mutationFn: optimisationApi.acknowledgeAlert,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['traj-alerts'] }),
  })

  return (
    <div>
      <PageHeader title="Campaign Optimisation"
        action={
          <div className="flex gap-2">
            <select className="input text-sm" value={selectedClient} onChange={e => setSelectedClient(e.target.value)}>
              <option value="">Select client…</option>
              {clients.map(c => <option key={c.id} value={c.id}>{c.company_name}</option>)}
            </select>
            <button onClick={() => selectedClient && trigger.mutate(selectedClient)}
              disabled={!selectedClient || trigger.isPending}
              className="btn-primary flex items-center gap-2">
              <Zap size={14}/> {trigger.isPending ? 'Analysing…' : 'Run Analysis'}
            </button>
          </div>
        }
      />

      <div className="flex gap-1 mb-6 bg-gray-100 p-1 rounded-xl w-fit">
        {[['runs','Optimisation Runs'],['alerts','Trajectory Alerts']].map(([key,label]) => (
          <button key={key} onClick={() => setTab(key)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === key ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500 hover:text-gray-700'}`}>
            {label} {key === 'alerts' && alerts.length > 0 && <span className="ml-1 bg-red-500 text-white text-xs rounded-full px-1.5">{alerts.length}</span>}
          </button>
        ))}
      </div>

      {tab === 'runs' && (
        <div className="space-y-4">
          {runs.map(run => (
            <div key={run.id} className="card p-5">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <p className="font-semibold text-gray-900">{run.client_name}</p>
                  <p className="text-xs text-gray-400">{new Date(run.created_at).toLocaleString('en-IN')}</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">{run.mode}</span>
                  <Badge status={run.status} />
                </div>
              </div>
              <div className="flex gap-4 text-sm text-gray-600">
                <span>{run.total_recommendations} recommendations</span>
                <span>{run.executed_count} executed</span>
              </div>
            </div>
          ))}
          {runs.length === 0 && <div className="card p-12 text-center text-gray-400">No optimisation runs yet.</div>}
        </div>
      )}

      {tab === 'alerts' && (
        <div className="space-y-3">
          {alerts.map(alert => (
            <div key={alert.id} className={`card p-5 border-l-4 ${alert.severity === 'critical' ? 'border-l-red-400' : 'border-l-amber-400'}`}>
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <AlertTriangle size={16} className={alert.severity === 'critical' ? 'text-red-500' : 'text-amber-500'} />
                    <p className="font-semibold text-gray-900">{alert.client_name}</p>
                    <Badge status={alert.severity} />
                  </div>
                  <p className="text-sm text-gray-600">
                    {alert.kpi_name?.toUpperCase()} projected at{' '}
                    <strong>{alert.projected_eom_value?.toFixed(2)}</strong> vs target{' '}
                    <strong>{alert.target_value}</strong>
                    {' '}({alert.gap_percentage?.toFixed(1)}% gap)
                  </p>
                  <p className="text-xs text-gray-400 mt-1">{alert.days_remaining} days remaining in month</p>
                </div>
                <button onClick={() => acknowledge.mutate(alert.id)} className="btn-secondary text-sm">
                  Acknowledge
                </button>
              </div>
            </div>
          ))}
          {alerts.length === 0 && <div className="card p-12 text-center text-gray-400">No trajectory alerts. All clients on track ✓</div>}
        </div>
      )}
    </div>
  )
}