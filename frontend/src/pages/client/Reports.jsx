import { useQuery } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import { PageHeader } from '../../components/ui/PageHeader'
import { Badge } from '../../components/ui/Badge'
import { reportingApi } from '../../api/modules'

const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

export default function ClientReports() {
  const { data: reports = [] } = useQuery({
    queryKey: ['client-reports'],
    queryFn: () => reportingApi.list(),
  })

  const download = async (id, clientName, month, year) => {
    const res = await reportingApi.downloadPdf(id)
    const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `report-${MONTHS[month-1]}-${year}.pdf`
    a.click()
  }

  return (
    <div>
      <PageHeader title="Performance Reports" />
      <div className="space-y-4">
        {reports.map(r => (
          <div key={r.id} className="card p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="font-semibold text-gray-900">{r.period_label}</p>
                <p className="text-sm text-gray-500 mt-1">{r.narrative?.slice(0, 120)}…</p>
                <div className="flex items-center gap-3 mt-3">
                  <Badge status={r.status} />
                  {r.delivered_at && (
                    <span className="text-xs text-gray-400">
                      Delivered {new Date(r.delivered_at).toLocaleDateString('en-IN')}
                    </span>
                  )}
                </div>
              </div>
              {r.has_pdf && (
                <button
                  onClick={() => download(r.id, r.client_name, r.period_start ? new Date(r.period_start).getMonth() + 1 : 1, r.period_start ? new Date(r.period_start).getFullYear() : 2026)}
                  className="flex items-center gap-2 btn-secondary text-sm"
                >
                  <Download size={15} /> PDF
                </button>
              )}
            </div>
          </div>
        ))}
        {reports.length === 0 && (
          <div className="card p-12 text-center text-gray-400">No reports yet</div>
        )}
      </div>
    </div>
  )
}