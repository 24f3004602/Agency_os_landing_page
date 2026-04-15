import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Sparkles } from 'lucide-react'
import { PageHeader } from '../../components/ui/PageHeader'
import { Badge } from '../../components/ui/Badge'
import { Modal } from '../../components/ui/Modal'
import { contentApi, clientApi } from '../../api/modules'

export default function OwnerContent() {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({
    client_id: '', title: '', objective: '', platform: 'instagram',
    content_type: 'social_post', tone_of_voice: 'professional',
    target_audience: '', key_message: '', num_variations: 3,
  })
  const qc = useQueryClient()

  const { data: briefs = [] } = useQuery({ queryKey: ['content-briefs'], queryFn: () => contentApi.listBriefs() })
  const { data: clients = [] } = useQuery({ queryKey: ['clients'], queryFn: () => clientApi.list() })
  const { data: approvals = [] } = useQuery({ queryKey: ['all-approvals'], queryFn: () => contentApi.listApprovals({ status: 'all' }) })

  const createBrief = useMutation({
    mutationFn: contentApi.createBrief,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['content-briefs'] }); setOpen(false) },
  })

  const generate = useMutation({
    mutationFn: (id) => contentApi.generate(id),
    onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ['content-briefs'] }), 35000),
  })

  const statusIcon = { draft: '📝', generating: '⚙️', ready: '✅', submitted: '📤', approved: '👍', published: '🚀' }

  return (
    <div>
      <PageHeader title="Content Pipeline" subtitle="Brief → Draft → Approve → Publish"
        action={<button onClick={() => setOpen(true)} className="btn-primary flex items-center gap-2"><Plus size={16}/>New Brief</button>} />

      {approvals.filter(a => a.status === 'pending').length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 mb-6">
          <p className="text-sm font-semibold text-amber-800">
            ⏳ {approvals.filter(a => a.status === 'pending').length} approval(s) waiting for client response
          </p>
        </div>
      )}

      <div className="space-y-3">
        {briefs.map(brief => (
          <div key={brief.id} className="card p-5">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <p className="text-xs text-gray-400 mb-1">{brief.client_name}</p>
                <div className="flex items-center gap-2">
                  <span className="text-lg">{statusIcon[brief.status] || '📄'}</span>
                  <p className="font-semibold text-gray-900">{brief.title}</p>
                </div>
                <div className="flex items-center gap-2 mt-2">
                  <Badge status={brief.platform} label={brief.platform} />
                  <Badge status={brief.content_type} label={brief.content_type?.replace(/_/g,' ')} />
                  <span className="text-xs text-gray-400">{brief.draft_count} draft{brief.draft_count !== 1 ? 's' : ''}</span>
                </div>
              </div>
              {brief.status === 'draft' && (
                <button onClick={() => generate.mutate(brief.id)} disabled={generate.isPending}
                  className="btn-primary text-sm flex items-center gap-1.5 flex-shrink-0">
                  <Sparkles size={14}/> Generate Drafts
                </button>
              )}
            </div>
          </div>
        ))}
        {briefs.length === 0 && (
          <div className="card p-12 text-center text-gray-400">
            No content briefs yet. Create your first brief.
          </div>
        )}
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title="New Content Brief" width="max-w-2xl">
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Client</label>
              <select className="input" value={form.client_id} onChange={e => setForm(f => ({...f, client_id: e.target.value}))}>
                <option value="">Select…</option>
                {clients.map(c => <option key={c.id} value={c.id}>{c.company_name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Platform</label>
              <select className="input" value={form.platform} onChange={e => setForm(f => ({...f, platform: e.target.value}))}>
                {['instagram','facebook','google_ads','email','linkedin'].map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Brief Title</label>
            <input className="input" value={form.title} onChange={e => setForm(f => ({...f, title: e.target.value}))} placeholder="e.g. Diwali Sale Instagram Campaign" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Objective *</label>
            <textarea className="input" rows={2} value={form.objective}
              onChange={e => setForm(f => ({...f, objective: e.target.value}))}
              placeholder="What should this content achieve?" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Tone</label>
              <select className="input" value={form.tone_of_voice} onChange={e => setForm(f => ({...f, tone_of_voice: e.target.value}))}>
                {['professional','casual','witty','urgent','inspirational','educational'].map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Variations</label>
              <select className="input" value={form.num_variations} onChange={e => setForm(f => ({...f, num_variations: +e.target.value}))}>
                {[1,2,3,4,5].map(n => <option key={n} value={n}>{n} variation{n !== 1 ? 's' : ''}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Target Audience</label>
            <input className="input" value={form.target_audience} onChange={e => setForm(f => ({...f, target_audience: e.target.value}))} placeholder="e.g. Women 25-40, urban India" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Key Message</label>
            <input className="input" value={form.key_message} onChange={e => setForm(f => ({...f, key_message: e.target.value}))} placeholder="The one thing you want them to remember" />
          </div>
          <div className="flex gap-3 pt-2">
            <button onClick={() => setOpen(false)} className="btn-secondary flex-1">Cancel</button>
            <button onClick={() => createBrief.mutate(form)} disabled={createBrief.isPending} className="btn-primary flex-1">
              {createBrief.isPending ? 'Creating…' : 'Create Brief'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}