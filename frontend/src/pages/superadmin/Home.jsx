import { useQuery } from '@tanstack/react-query'
import { Building2, Activity, Package } from 'lucide-react'
import { PageHeader } from '../../components/ui/PageHeader'
import { StatCard } from '../../components/ui/card'
import { superadminApi } from '../../api/modules'

export default function SuperAdminHome() {
  const { data: agencies = [] } = useQuery({
    queryKey: ['agencies'],
    queryFn: superadminApi.listAgencies,
  })

  const active = agencies.filter(a => a.status === 'active').length
  const trial = agencies.filter(a => a.status === 'trial').length
  const totalModules = agencies.reduce(
    (sum, a) => sum + (a.active_modules?.length || 0), 0
  )

  return (
    <div>
      <PageHeader title="System Overview" subtitle="Agency OS platform health" />
      <div className="grid grid-cols-3 gap-4 mb-8">
        <StatCard label="Total Agencies" value={agencies.length} icon={Building2} color="blue" />
        <StatCard label="Active" value={active} sub={`${trial} on trial`} icon={Activity} color="green" />
        <StatCard label="Modules Activated" value={totalModules} icon={Package} color="purple" />
      </div>
      <div className="card p-6">
        <h2 className="font-semibold text-gray-900 mb-4">Recent Agencies</h2>
        <div className="space-y-3">
          {agencies.slice(0, 5).map(agency => (
            <div key={agency.id} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
              <div>
                <p className="font-medium text-gray-900">{agency.name}</p>
                <p className="text-xs text-gray-500">{agency.owner_email}</p>
              </div>
              <div className="flex items-center gap-2">
                {agency.active_modules?.map(m => (
                  <span key={m} className="badge-blue text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-600 font-medium">{m}</span>
                ))}
                <span className={`badge ${agency.status === 'active' ? 'badge-green' : 'badge-amber'}`}>
                  {agency.status}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}