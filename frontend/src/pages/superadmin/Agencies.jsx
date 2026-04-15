import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { PageHeader } from '../../components/ui/PageHeader'
import { Table } from '../../components/ui/Table'
import { Badge } from '../../components/ui/Badge'
import { Modal } from '../../components/ui/Modal'
import { superadminApi } from '../../api/modules'

export default function SuperAdminAgencies() {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({
    agency_name: '', owner_full_name: '', owner_email: '',
    owner_password: '', plan_tier: 'trial',
    modules_to_activate: ['M1'],
  })
  const [error, setError] = useState('')
  const qc = useQueryClient()

  const { data: agencies = [], isLoading } = useQuery({
    queryKey: ['agencies'],
    queryFn: superadminApi.listAgencies,
  })

  const create = useMutation({
    mutationFn: superadminApi.createAgency,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agencies'] })
      setOpen(false)
      setForm({
        agency_name: '', owner_full_name: '', owner_email: '',
        owner_password: '', plan_tier: 'trial',
        modules_to_activate: ['M1'],
      })
    },
    onError: (e) => {
  const detail = e.response?.data?.detail

  if (Array.isArray(detail)) {
    // Extract readable messages
    const msg = detail.map(err => err.msg).join(', ')
    setError(msg)
  } else {
    setError(detail || 'Failed')
  }
}
  })

  const toggleModule = (m) => {
    setForm(f => ({
      ...f,
      modules_to_activate: f.modules_to_activate.includes(m)
        ? f.modules_to_activate.filter(x => x !== m)
        : [...f.modules_to_activate, m],
    }))
  }

  const modules = ['M1','M2','M3','M4','M5','M6','M7','M8','M9','M10','M11']

  return (
    <div>
      <PageHeader
        title="Agency Management"
        subtitle="All tenants on the platform"
        action={
          <button onClick={() => setOpen(true)} className="btn-primary flex items-center gap-2">
            <Plus size={16} /> New Agency
          </button>
        }
      />

      <div className="card" style={{padding: 0}}>
        {isLoading ? (
          <div className="p-8 text-center text-gray-400">Loading…</div>
        ) : (
          <Table
            headers={['Agency', 'Owner', 'Modules', 'Status', 'Created']}
            rows={agencies.map(a => [
              <span className="font-medium">{a.name}</span>,
              <span className="text-gray-500 text-xs">{a.owner_email}</span>,
              <div className="flex gap-1 flex-wrap">
                {(a.active_modules || []).map(m => (
                  <span key={m} className="text-xs bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded font-medium">{m}</span>
                ))}
              </div>,
              <Badge status={a.status} />,
              <span className="text-xs text-gray-400">
                {new Date(a.created_at).toLocaleDateString('en-IN')}
              </span>,
            ])}
          />
        )}
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title="Create New Agency">
        <div className="space-y-4">
          {[
            ['Agency Name', 'agency_name', 'text'],
            ['Owner Full Name', 'owner_full_name', 'text'],
            ['Owner Email', 'owner_email', 'email'],
            ['Owner Password', 'owner_password', 'password'],
          ].map(([label, key, type]) => (
            <div key={key}>
              <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
              <input
                type={type}
                className="input"
                value={form[key]}
                onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
              />
            </div>
          ))}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Modules to Activate
            </label>
            <div className="flex flex-wrap gap-2">
              {modules.map(m => (
                <button
                  key={m}
                  type="button"
                  onClick={() => toggleModule(m)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    form.modules_to_activate.includes(m)
                      ? 'bg-brand-500 text-white'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 rounded-lg px-4 py-2">{error}</p>
          )}

          <div className="flex gap-3 pt-2">
            <button onClick={() => setOpen(false)} className="btn-secondary flex-1">Cancel</button>
            <button
              onClick={() => create.mutate(form)}
              disabled={create.isPending}
              className="btn-primary flex-1"
            >
              {create.isPending ? 'Creating…' : 'Create Agency'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}