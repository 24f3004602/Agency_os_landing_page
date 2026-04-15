import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, RefreshCw } from 'lucide-react'
import { PageHeader } from '../../components/ui/PageHeader'
import { Table } from '../../components/ui/Table'
import { Badge } from '../../components/ui/Badge'
import { Modal } from '../../components/ui/Modal'
import { leadsApi } from '../../api/modules'

export default function OwnerLeads() {
  const [openModal, setOpenModal] = useState(false)
  const [form, setForm] = useState({
    full_name: '', email: '', company_name: '', designation: '',
    industry: '', monthly_ad_budget: '', pain_points: '', source: 'manual',
  })
  const qc = useQueryClient()

  const { data: leads = [], isLoading } = useQuery({
    queryKey: ['leads'],
    queryFn: () => leadsApi.listLeads(),
  })

  const create = useMutation({
    mutationFn: leadsApi.createLead,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['leads'] }); setOpenModal(false) },
  })

  const rescore = useMutation({
    mutationFn: leadsApi.rescore,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['leads'] }),
  })

  const scoreColor = (score) => {
    if (!score) return 'text-gray-400'
    if (score >= 80) return 'text-green-600 font-bold'
    if (score >= 60) return 'text-amber-600 font-semibold'
    return 'text-red-500'
  }

  return (
    <div>
      <PageHeader
        title="Lead Dashboard"
        subtitle="Sorted by ICP score — highest fit first"
        action={
          <button onClick={() => setOpenModal(true)} className="btn-primary flex items-center gap-2">
            <Plus size={16} /> Add Lead
          </button>
        }
      />

      <div className="card" style={{padding:0}}>
        {isLoading ? (
          <div className="p-8 text-center text-gray-400">Loading…</div>
        ) : (
          <Table
            headers={['Name', 'Company', 'Industry', 'Budget', 'ICP Score', 'Status', '']}
            rows={leads.map(l => [
              <div>
                <p className="font-medium">{l.full_name}</p>
                <p className="text-xs text-gray-400">{l.designation}</p>
              </div>,
              l.company_name,
              l.industry || '—',
              l.monthly_ad_budget || '—',
              <span className={scoreColor(l.icp_score)}>
                {l.icp_score ? `${Math.round(l.icp_score)}/100` : 'Scoring…'}
              </span>,
              <Badge status={l.status} />,
              <button
                onClick={() => rescore.mutate(l.id)}
                className="text-gray-400 hover:text-gray-700"
                title="Re-score"
              >
                <RefreshCw size={14} />
              </button>,
            ])}
            empty="No leads yet."
          />
        )}
      </div>

      <Modal open={openModal} onClose={() => setOpenModal(false)} title="Add Lead">
        <div className="space-y-4">
          {[
            ['Full Name', 'full_name'], ['Email', 'email'],
            ['Company', 'company_name'], ['Designation', 'designation'],
            ['Industry', 'industry'], ['Monthly Ad Budget', 'monthly_ad_budget'],
          ].map(([label, key]) => (
            <div key={key}>
              <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
              <input className="input" value={form[key]}
                onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} />
            </div>
          ))}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Pain Points</label>
            <textarea className="input" rows={3} value={form.pain_points}
              onChange={e => setForm(f => ({ ...f, pain_points: e.target.value }))} />
          </div>
          <div className="flex gap-3 pt-2">
            <button onClick={() => setOpenModal(false)} className="btn-secondary flex-1">Cancel</button>
            <button onClick={() => create.mutate(form)} disabled={create.isPending} className="btn-primary flex-1">
              {create.isPending ? 'Adding…' : 'Add & Score'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}