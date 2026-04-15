import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Plus, Download } from 'lucide-react'
import { PageHeader } from '../../components/ui/PageHeader'
import { Table } from '../../components/ui/Table'
import { Badge } from '../../components/ui/Badge'
import { Modal } from '../../components/ui/Modal'
import { reportingApi, clientApi } from '../../api/modules'

export default function OwnerReports() {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ client_id: '', period_start: '', period_end: '' })
  const qc = useQueryClient()

  const { data: reports = [] } = useQuery({ queryKey: ['reports'], queryFn: () => reportingApi.list() })
  const { data: clients = [] } = useQuery({ queryKey: ['clients'], queryFn: () => clientApi.list() })

  const generate = useMutation({
    mutationFn: reportingApi.generate,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['reports'] }); setOpen(false) },
  })

  const downloadPdf = async (id) => {
    const res = await reportingApi.downloadPdf(id)
    const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
    const a = document.createElement('a'); a.href = url; a.download = `report-${id.slice(0,8)}.pdf`; a.click()
  }

  return (
    <div>
      <PageHeader title="Reports"
        action={<button onClick={() => setOpen(true)} className="btn-primary flex items-center gap-2"><Plus size={16}/> Generate Report</button>} />
      <div className="card" style={{padding:0}}>
        <Table
          headers={['Client','Period','Status','Delivered','']}
          rows={reports.map(r => [
            r.client_name,
            r.period_label,
            <Badge status={r.status} />,
            r.delivered_at ? new Date(r.delivered_at).toLocaleDateString('en-IN') : '—',
            r.has_pdf ? <button onClick={() => downloadPdf(r.id)} className="text-gray-400 hover:text-gray-900"><Download size={15}/></button> : '—',
          ])}
          empty="No reports yet."
        />
      </div>
      <Modal open={open} onClose={() => setOpen(false)} title="Generate Report">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Client</label>
            <select className="input" value={form.client_id} onChange={e => setForm(f => ({...f, client_id: e.target.value}))}>
              <option value="">Select…</option>
              {clients.map(c => <option key={c.id} value={c.id}>{c.company_name}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Period Start</label>
              <input type="date" className="input" value={form.period_start} onChange={e => setForm(f => ({...f, period_start: e.target.value}))} />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Period End</label>
              <input type="date" className="input" value={form.period_end} onChange={e => setForm(f => ({...f, period_end: e.target.value}))} />
            </div>
          </div>
          <div className="flex gap-3 pt-2">
            <button onClick={() => setOpen(false)} className="btn-secondary flex-1">Cancel</button>
            <button onClick={() => generate.mutate({ ...form, period_start: new Date(form.period_start).toISOString(), period_end: new Date(form.period_end).toISOString() })} disabled={generate.isPending} className="btn-primary flex-1">
              {generate.isPending ? 'Generating…' : 'Generate'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}