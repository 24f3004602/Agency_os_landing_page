import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { PageHeader } from '../../components/ui/PageHeader'
import { Table } from '../../components/ui/Table'
import { Badge } from '../../components/ui/Badge'
import { Modal } from '../../components/ui/Modal'
import { clientApi, employeeApi } from '../../api/modules'

export default function OwnerClients() {
  const [openModal, setOpenModal] = useState(false)
  const [form, setForm] = useState({
    company_name: '', contact_name: '', contact_email: '',
    contact_phone: '', account_manager_id: '',
  })
  const qc = useQueryClient()

  const { data: clients = [] } = useQuery({ queryKey: ['clients'], queryFn: () => clientApi.list() })
  const { data: employees = [] } = useQuery({ queryKey: ['employees'], queryFn: () => employeeApi.list() })

  const createClient = useMutation({
    mutationFn: clientApi.create,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['clients'] }); setOpenModal(false) },
  })

  return (
    <div>
      <PageHeader
        title="Clients"
        action={
          <button onClick={() => setOpenModal(true)} className="btn-primary flex items-center gap-2">
            <Plus size={16} /> Add Client
          </button>
        }
      />

      <div className="card" style={{padding:0}}>
        <Table
          headers={['Company', 'Contact', 'Account Manager', 'Status']}
          rows={clients.map(c => [
            <span className="font-medium">{c.company_name}</span>,
            <div>
              <p className="text-sm">{c.contact_name}</p>
              <p className="text-xs text-gray-400">{c.contact_email}</p>
            </div>,
            c.account_manager_name || '—',
            <Badge status={c.status} />,
          ])}
          empty="No clients yet."
        />
      </div>

      <Modal open={openModal} onClose={() => setOpenModal(false)} title="Add Client">
        <div className="space-y-4">
          {[
            ['Company Name', 'company_name'],
            ['Contact Name', 'contact_name'],
            ['Contact Email', 'contact_email'],
            ['Contact Phone', 'contact_phone'],
          ].map(([label, key]) => (
            <div key={key}>
              <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
              <input className="input" value={form[key]}
                onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} />
            </div>
          ))}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Account Manager</label>
            <select className="input" value={form.account_manager_id}
              onChange={e => setForm(f => ({ ...f, account_manager_id: e.target.value }))}>
              <option value="">None</option>
              {employees.map(e => (
                <option key={e.id} value={e.id}>{e.full_name}</option>
              ))}
            </select>
          </div>
          <div className="flex gap-3 pt-2">
            <button onClick={() => setOpenModal(false)} className="btn-secondary flex-1">Cancel</button>
            <button
              onClick={() => createClient.mutate({
                ...form,
                account_manager_id: form.account_manager_id || undefined,
              })}
              disabled={createClient.isPending}
              className="btn-primary flex-1"
            >
              {createClient.isPending ? 'Adding…' : 'Add Client'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}