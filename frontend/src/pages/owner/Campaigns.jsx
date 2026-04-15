import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { PageHeader } from '../../components/ui/PageHeader'
import { Badge } from '../../components/ui/Badge'
import { Modal } from '../../components/ui/Modal'
import { campaignApi, clientApi } from '../../api/modules'

export default function OwnerCampaigns() {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ client_id: '', name: '', platform: 'meta', description: '' })
  const qc = useQueryClient()

  const { data: campaigns = [] } = useQuery({ queryKey: ['campaigns'], queryFn: () => campaignApi.list() })
  const { data: clients = [] } = useQuery({ queryKey: ['clients'], queryFn: () => clientApi.list() })

  const create = useMutation({
    mutationFn: campaignApi.create,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['campaigns'] }); setOpen(false) },
  })

  const platforms = ['meta', 'google_ads', 'email', 'social', 'content', 'multi_channel']

  return (
    <div>
      <PageHeader title="Campaigns" subtitle="Campaign deliverables and content pipeline"
        action={<button onClick={() => setOpen(true)} className="btn-primary flex items-center gap-2"><Plus size={16}/>New Campaign</button>} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {campaigns.map(c => (
          <div key={c.id} className="card p-5">
            <div className="flex items-start justify-between mb-3">
              <div>
                <p className="text-xs text-gray-400 mb-1">{c.client_name}</p>
                <p className="font-semibold text-gray-900">{c.name}</p>
              </div>
              <div className="flex items-center gap-2">
                <Badge status={c.platform} label={c.platform?.replace(/_/g,' ')} />
                <Badge status={c.status} />
              </div>
            </div>
            <div className="flex items-center justify-between">
              <p className="text-sm text-gray-500">{c.task_count} task{c.task_count !== 1 ? 's' : ''}</p>
              <div className="flex gap-2">
                {Object.entries(c.tasks_by_status || {}).map(([status, count]) => (
                  <span key={status} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                    {status}: {count}
                  </span>
                ))}
              </div>
            </div>
          </div>
        ))}
        {campaigns.length === 0 && (
          <div className="col-span-2 card p-12 text-center text-gray-400">
            No campaigns yet. Create your first campaign.
          </div>
        )}
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title="New Campaign">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Client</label>
            <select className="input" value={form.client_id}
              onChange={e => setForm(f => ({...f, client_id: e.target.value}))}>
              <option value="">Select client…</option>
              {clients.map(c => <option key={c.id} value={c.id}>{c.company_name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Campaign Name</label>
            <input className="input" value={form.name}
              onChange={e => setForm(f => ({...f, name: e.target.value}))} placeholder="e.g. Diwali Sale 2026" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Platform</label>
            <select className="input" value={form.platform}
              onChange={e => setForm(f => ({...f, platform: e.target.value}))}>
              {platforms.map(p => <option key={p} value={p}>{p.replace(/_/g,' ')}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea className="input" rows={2} value={form.description}
              onChange={e => setForm(f => ({...f, description: e.target.value}))} />
          </div>
          <div className="flex gap-3 pt-2">
            <button onClick={() => setOpen(false)} className="btn-secondary flex-1">Cancel</button>
            <button onClick={() => create.mutate(form)} disabled={create.isPending} className="btn-primary flex-1">
              {create.isPending ? 'Creating…' : 'Create Campaign'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}