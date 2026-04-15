import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Zap } from 'lucide-react'
import { PageHeader } from '../../components/ui/PageHeader'
import { Badge } from '../../components/ui/Badge'
import { Modal } from '../../components/ui/Modal'
import { abmApi } from '../../api/modules'

export default function OwnerAbm() {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ company_name: '', industry: '', contact_name: '', contact_email: '', contact_phone: '' })
  const qc = useQueryClient()

  const { data: accounts = [] } = useQuery({ queryKey: ['abm-feed'], queryFn: abmApi.feed })

  const create = useMutation({
    mutationFn: abmApi.createAccount,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['abm-feed'] }); setOpen(false) },
  })

  const orchestrate = useMutation({
    mutationFn: abmApi.orchestrate,
    onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ['abm-feed'] }), 25000),
  })

  const stageColors = {
    identified: 'bg-gray-100 text-gray-600',
    researching: 'bg-blue-100 text-blue-700',
    first_touch: 'bg-purple-100 text-purple-700',
    engaged: 'bg-green-100 text-green-700',
    proposal: 'bg-amber-100 text-amber-700',
    closed_won: 'bg-green-200 text-green-800',
    closed_lost: 'bg-red-100 text-red-600',
  }

  return (
    <div>
      <PageHeader title="ABM Pipeline" subtitle="Account-based marketing — sorted by most stale"
        action={<button onClick={() => setOpen(true)} className="btn-primary flex items-center gap-2"><Plus size={16}/>Add Account</button>} />

      <div className="space-y-3">
        {accounts.map(account => (
          <div key={account.id} className="card p-5">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-3 mb-1">
                  <p className="font-semibold text-gray-900">{account.company_name}</p>
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${stageColors[account.stage] || 'bg-gray-100 text-gray-600'}`}>
                    {account.stage?.replace(/_/g,' ')}
                  </span>
                </div>
                {account.industry && <p className="text-sm text-gray-500">{account.industry}</p>}
                {account.ai_next_action && (
                  <p className="text-xs text-brand-600 mt-2 bg-brand-50 px-3 py-1.5 rounded-lg">
                    💡 {account.ai_next_action}
                  </p>
                )}
                <p className="text-xs text-gray-400 mt-2">
                  {account.total_touches} touches ·{' '}
                  {account.days_since_last_touch != null
                    ? `${account.days_since_last_touch} days since last touch`
                    : 'never touched'}
                </p>
              </div>
              <button
                onClick={() => orchestrate.mutate(account.id)}
                disabled={orchestrate.isPending}
                className="btn-primary text-sm flex items-center gap-1.5 flex-shrink-0"
                title="Run AI orchestration"
              >
                <Zap size={14}/> Orchestrate
              </button>
            </div>
          </div>
        ))}
        {accounts.length === 0 && (
          <div className="card p-12 text-center text-gray-400">
            No ABM accounts yet. Add your first target account.
          </div>
        )}
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title="Add Target Account">
        <div className="space-y-4">
          {[['Company Name','company_name'],['Industry','industry'],['Contact Name','contact_name'],['Contact Email','contact_email'],['Contact Phone','contact_phone']].map(([label,key]) => (
            <div key={key}>
              <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
              <input className="input" value={form[key]} onChange={e => setForm(f => ({...f, [key]: e.target.value}))} />
            </div>
          ))}
          <div className="flex gap-3 pt-2">
            <button onClick={() => setOpen(false)} className="btn-secondary flex-1">Cancel</button>
            <button onClick={() => create.mutate(form)} disabled={create.isPending} className="btn-primary flex-1">
              {create.isPending ? 'Adding…' : 'Add Account'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}