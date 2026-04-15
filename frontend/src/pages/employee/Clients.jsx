import { useQuery } from '@tanstack/react-query'
import { PageHeader } from '../../components/ui/PageHeader'
import { clientApi, commApi } from '../../api/modules'

export default function EmployeeClients() {
  const { data: clients = [] } = useQuery({
    queryKey: ['clients'],
    queryFn: () => clientApi.list(),
  })

  return (
    <div>
      <PageHeader title="My Clients" />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {clients.map(c => (
          <div key={c.id} className="card p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="font-semibold text-gray-900">{c.company_name}</p>
                <p className="text-sm text-gray-500">{c.contact_name}</p>
                <p className="text-xs text-gray-400 mt-1">{c.contact_email}</p>
              </div>
              <span className={`badge ${c.status === 'active' ? 'badge-green' : c.status === 'at_risk' ? 'badge-amber' : 'badge-gray'}`}>
                {c.status?.replace(/_/g,' ')}
              </span>
            </div>
          </div>
        ))}
        {clients.length === 0 && (
          <div className="col-span-2 card p-12 text-center text-gray-400">
            No clients assigned to you
          </div>
        )}
      </div>
    </div>
  )
}