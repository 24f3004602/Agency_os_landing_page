import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Play } from 'lucide-react'
import { PageHeader } from '../../components/ui/PageHeader'
import { Modal } from '../../components/ui/Modal'
import { researchApi, clientApi } from '../../api/modules'

export default function OwnerResearch() {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ client_id: '', competitor_name: '', domain: '', industry: '' })
  const [selectedClient, setSelectedClient] = useState('')
  const qc = useQueryClient()

  const { data: briefs = [] } = useQuery({ queryKey: ['research-briefs'], queryFn: () => researchApi.listBriefs() })
  const { data: clients = [] } = useQuery({ queryKey: ['clients'], queryFn: () => clientApi.list() })

  const addCompetitor = useMutation({
    mutationFn: researchApi.addCompetitor,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['research-briefs'] }); setOpen(false) },
  })

  const runResearch = useMutation({
    mutationFn: ({ client_id }) => researchApi.runResearch({ client_id }),
    onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ['research-briefs'] }), 30000),
  })

  return (
    <div>
      <PageHeader title="Competitive Research" subtitle="AI-generated competitive intelligence"
        action={
          <div className="flex gap-2">
            <select className="input text-sm" value={selectedClient} onChange={e => setSelectedClient(e.target.value)}>
              <option value="">Select client to run…</option>
              {clients.map(c => <option key={c.id} value={c.id}>{c.company_name}</option>)}
            </select>
            <button onClick={() => selectedClient && runResearch.mutate({ client_id: selectedClient })}
              disabled={!selectedClient || runResearch.isPending}
              className="btn-primary flex items-center gap-2">
              <Play size={14}/> {runResearch.isPending ? 'Running…' : 'Run Research'}
            </button>
            <button onClick={() => setOpen(true)} className="btn-secondary flex items-center gap-2">
              <Plus size={16}/> Add Competitor
            </button>
          </div>
        }
      />

      <div className="space-y-4">
        {briefs.map(brief => (
          <div key={brief.id} className="card p-5">
            <div className="flex items-start justify-between mb-3">
              <div>
                <p className="text-xs text-gray-400 mb-1">{brief.client_name}</p>
                <p className="font-semibold text-gray-900">{brief.competitor_name}</p>
                <p className="text-xs text-gray-400 mt-0.5">
                  {new Date(brief.created_at).toLocaleDateString('en-IN')}
                </p>
              </div>
              {brief.acted_on && (
                <span className="badge-green text-xs">Acted On</span>
              )}
            </div>
            <div className="space-y-1">
              {(brief.key_findings || []).slice(0, 3).map((f, i) => (
                <p key={i} className="text-sm text-gray-600 flex items-start gap-2">
                  <span className="text-brand-500 mt-0.5 flex-shrink-0">•</span>{f}
                </p>
              ))}
            </div>
          </div>
        ))}
        {briefs.length === 0 && (
          <div className="card p-12 text-center text-gray-400">
            No research briefs yet. Add competitors and run research.
          </div>
        )}
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title="Add Competitor">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Client</label>
            <select className="input" value={form.client_id} onChange={e => setForm(f => ({...f, client_id: e.target.value}))}>
              <option value="">Select client…</option>
              {clients.map(c => <option key={c.id} value={c.id}>{c.company_name}</option>)}
            </select>
          </div>
          {[['Competitor Name','competitor_name'],['Domain (e.g. zomato.com)','domain'],['Industry','industry']].map(([label,key]) => (
            <div key={key}>
              <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
              <input className="input" value={form[key]} onChange={e => setForm(f => ({...f, [key]: e.target.value}))} />
            </div>
          ))}
          <div className="flex gap-3 pt-2">
            <button onClick={() => setOpen(false)} className="btn-secondary flex-1">Cancel</button>
            <button onClick={() => addCompetitor.mutate(form)} disabled={addCompetitor.isPending} className="btn-primary flex-1">
              {addCompetitor.isPending ? 'Adding…' : 'Add Competitor'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}