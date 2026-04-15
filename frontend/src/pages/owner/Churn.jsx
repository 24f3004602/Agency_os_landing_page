import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { PageHeader } from '../../components/ui/PageHeader'
import { Badge } from '../../components/ui/Badge'
import { Modal } from '../../components/ui/Modal'
import { churnApi } from '../../api/modules'

export default function OwnerChurn() {
  const [tab, setTab] = useState('alerts')
  const [resolveModal, setResolveModal] = useState(null)
  const [note, setNote] = useState('')
  const qc = useQueryClient()

  const { data: alerts = [] } = useQuery({ queryKey: ['churn-alerts'], queryFn: () => churnApi.listAlerts() })
  const { data: scores = [] } = useQuery({ queryKey: ['risk-scores'], queryFn: churnApi.riskScores })

  const resolve = useMutation({
    mutationFn: ({ id, resolution, note }) => churnApi.resolveAlert(id, { resolution, note }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['churn-alerts'] }); setResolveModal(null) },
  })

  const scoreColor = (score) => {
    if (score >= 70) return 'text-red-600 font-bold'
    if (score >= 40) return 'text-amber-600 font-semibold'
    return 'text-green-600'
  }

  return (
    <div>
      <PageHeader title="Churn Prevention" subtitle="AI-monitored client health" />

      <div className="flex gap-1 mb-6 bg-gray-100 p-1 rounded-xl w-fit">
        {[['alerts','Open Alerts'],['scores','Risk Scores']].map(([key,label]) => (
          <button key={key} onClick={() => setTab(key)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === key ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500 hover:text-gray-700'}`}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'alerts' && (
        <div className="space-y-4">
          {alerts.map(alert => (
            <div key={alert.id} className={`card p-5 border-l-4 ${alert.risk_score >= 70 ? 'border-l-red-400' : 'border-l-amber-400'}`}>
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <p className="font-semibold text-gray-900">{alert.client_name}</p>
                    <span className={`text-lg font-bold ${scoreColor(alert.risk_score)}`}>
                      {Math.round(alert.risk_score)}/100
                    </span>
                    <Badge status={alert.client_status} />
                  </div>
                  <div className="space-y-1 mb-3">
                    {(alert.trigger_reasons || []).map((r, i) => (
                      <p key={i} className="text-sm text-gray-600 flex items-start gap-2">
                        <span className="text-red-400 mt-0.5">•</span>{r}
                      </p>
                    ))}
                  </div>
                  {(alert.retention_actions || []).length > 0 && (
                    <div className="bg-blue-50 rounded-lg p-3">
                      <p className="text-xs font-semibold text-blue-700 mb-1">Suggested Actions:</p>
                      {alert.retention_actions.map((a, i) => (
                        <p key={i} className="text-xs text-blue-600">{i+1}. {a}</p>
                      ))}
                    </div>
                  )}
                </div>
                <button onClick={() => { setResolveModal(alert); setNote('') }}
                  className="btn-secondary text-sm flex-shrink-0">
                  Resolve
                </button>
              </div>
            </div>
          ))}
          {alerts.length === 0 && (
            <div className="card p-12 text-center text-gray-400">
              No open churn alerts. All clients are healthy ✓
            </div>
          )}
        </div>
      )}

      {tab === 'scores' && (
        <div className="card" style={{padding:0}}>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200">
                {['Client','Status','Risk Score','Open Alerts','Last Alert'].map(h => (
                  <th key={h} className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {scores.map(s => (
                <tr key={s.client_id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="py-3 px-4 font-medium">{s.client_name}</td>
                  <td className="py-3 px-4"><Badge status={s.client_status} /></td>
                  <td className="py-3 px-4">
                    {s.risk_score != null
                      ? <span className={scoreColor(s.risk_score)}>{Math.round(s.risk_score)}/100</span>
                      : <span className="text-gray-400">Not scanned</span>}
                  </td>
                  <td className="py-3 px-4">{s.open_alerts}</td>
                  <td className="py-3 px-4 text-gray-400 text-xs">
                    {s.last_alert_at ? new Date(s.last_alert_at).toLocaleDateString('en-IN') : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={!!resolveModal} onClose={() => setResolveModal(null)} title="Resolve Alert">
        <div className="space-y-4">
          <p className="text-sm text-gray-600">Resolving alert for <strong>{resolveModal?.client_name}</strong></p>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Resolution Note</label>
            <textarea className="input" rows={3} placeholder="What action was taken?" value={note}
              onChange={e => setNote(e.target.value)} />
          </div>
          <div className="flex gap-3 pt-2">
            <button onClick={() => resolve.mutate({ id: resolveModal.id, resolution: 'false_positive', note })}
              className="btn-secondary flex-1 text-sm">False Positive</button>
            <button onClick={() => resolve.mutate({ id: resolveModal.id, resolution: 'resolved', note })}
              disabled={resolve.isPending} className="btn-primary flex-1">
              {resolve.isPending ? 'Resolving…' : 'Mark Resolved'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}