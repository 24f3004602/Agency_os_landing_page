import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, ChevronRight } from 'lucide-react'
import { PageHeader } from '../../components/ui/PageHeader'
import { Badge } from '../../components/ui/Badge'
import { Modal } from '../../components/ui/Modal'
import { outreachApi, leadsApi } from '../../api/modules'

export default function OwnerOutreach() {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ lead_id: '', send_mode: 'manual' })
  const qc = useQueryClient()

  const { data: sequences = [] } = useQuery({ queryKey: ['sequences'], queryFn: () => outreachApi.listSequences() })
  const { data: leads = [] } = useQuery({ queryKey: ['leads'], queryFn: () => leadsApi.listLeads({ status: 'scored' }) })

  const create = useMutation({
    mutationFn: outreachApi.createSequence,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sequences'] }); setOpen(false) },
  })

  const pause = useMutation({
    mutationFn: outreachApi.pause,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sequences'] }),
  })

  const statusColor = { active: 'border-l-green-400', paused: 'border-l-gray-300', replied: 'border-l-blue-400', completed: 'border-l-gray-200' }

  return (
    <div>
      <PageHeader title="Outreach Sequences" subtitle="AI-personalised multi-step outreach"
        action={<button onClick={() => setOpen(true)} className="btn-primary flex items-center gap-2"><Plus size={16}/>New Sequence</button>} />

      <div className="space-y-3">
        {sequences.map(seq => (
          <div key={seq.id} className={`card p-5 border-l-4 ${statusColor[seq.status] || 'border-l-gray-200'}`}>
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold text-gray-900">{seq.lead_name}</p>
                <p className="text-sm text-gray-500">{seq.lead_company}</p>
                <div className="flex items-center gap-3 mt-2">
                  <Badge status={seq.status} />
                  <span className="text-xs text-gray-400">
                    Step {seq.current_step}/{seq.total_steps} · {seq.send_mode} mode
                  </span>
                  {seq.icp_score_at_creation && (
                    <span className="text-xs text-gray-400">ICP: {Math.round(seq.icp_score_at_creation)}/100</span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {seq.status === 'active' && (
                  <button onClick={() => pause.mutate(seq.id)} className="btn-secondary text-sm py-1.5">Pause</button>
                )}
                <ChevronRight size={18} className="text-gray-400" />
              </div>
            </div>
          </div>
        ))}
        {sequences.length === 0 && (
          <div className="card p-12 text-center text-gray-400">
            No sequences yet. Create one for a high-score lead.
          </div>
        )}
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title="Create Outreach Sequence">
        <div className="space-y-4">
          <p className="text-sm text-gray-500">
            The AI will retrieve competitor intel from M6 and the lead's ICP score from M7
            to write personalised 3-step outreach automatically.
          </p>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Lead</label>
            <select className="input" value={form.lead_id} onChange={e => setForm(f => ({...f, lead_id: e.target.value}))}>
              <option value="">Select lead…</option>
              {leads.map(l => (
                <option key={l.id} value={l.id}>
                  {l.full_name} — {l.company_name} {l.icp_score ? `(${Math.round(l.icp_score)}/100)` : ''}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Send Mode</label>
            <select className="input" value={form.send_mode} onChange={e => setForm(f => ({...f, send_mode: e.target.value}))}>
              <option value="manual">Manual — AE reviews each step</option>
              <option value="auto">Auto — sends on schedule</option>
            </select>
          </div>
          <div className="flex gap-3 pt-2">
            <button onClick={() => setOpen(false)} className="btn-secondary flex-1">Cancel</button>
            <button onClick={() => create.mutate(form)} disabled={create.isPending || !form.lead_id} className="btn-primary flex-1">
              {create.isPending ? 'Generating…' : 'Generate Sequence'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}