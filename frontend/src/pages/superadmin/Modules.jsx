import { useQuery } from '@tanstack/react-query'
import { PageHeader } from '../../components/ui/PageHeader'
import { superadminApi } from '../../api/modules'

const ALL_MODULES = ['M1','M2','M3','M4','M5','M6','M7','M8','M9','M10','M11']

export default function SuperAdminModules() {
  const { data: agencies = [] } = useQuery({
    queryKey: ['agencies'],
    queryFn: superadminApi.listAgencies,
  })

  return (
    <div>
      <PageHeader title="Module Control Centre" subtitle="Active modules per agency" />
      <div className="card overflow-x-auto" style={{padding:0}}>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase tracking-wide sticky left-0 bg-white">
                Agency
              </th>
              {ALL_MODULES.map(m => (
                <th key={m} className="text-center py-3 px-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  {m}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {agencies.map(agency => (
              <tr key={agency.id} className="border-b border-gray-100 hover:bg-gray-50">
                <td className="py-3 px-4 sticky left-0 bg-white font-medium text-gray-900">
                  {agency.name}
                </td>
                {ALL_MODULES.map(m => {
                  const active = (agency.active_modules || []).includes(m)
                  return (
                    <td key={m} className="text-center py-3 px-3">
                      <div className={`inline-flex w-5 h-5 rounded-full items-center justify-center mx-auto ${active ? 'bg-green-500' : 'bg-gray-200'}`}>
                        {active && (
                          <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                          </svg>
                        )}
                      </div>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}