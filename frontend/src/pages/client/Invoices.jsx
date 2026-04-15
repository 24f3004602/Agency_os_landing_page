import { useQuery } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import { PageHeader } from '../../components/ui/PageHeader'
import { Badge } from '../../components/ui/Badge'
import { operationsApi } from '../../api/modules'

export default function ClientInvoices() {
  const { data: invoices = [] } = useQuery({
    queryKey: ['client-invoices'],
    queryFn: () => operationsApi.listInvoices(),
  })

  const download = async (id, num) => {
    const res = await operationsApi.downloadInvoice(id)
    const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
    const a = document.createElement('a'); a.href = url; a.download = `${num}.pdf`; a.click()
  }

  return (
    <div>
      <PageHeader title="Invoices" />
      <div className="space-y-3">
        {invoices.map(inv => (
          <div key={inv.id} className="card p-5 flex items-center justify-between">
            <div>
              <p className="font-semibold text-gray-900">{inv.invoice_number}</p>
              <p className="text-sm text-gray-500">
                ₹{Number(inv.total_amount).toLocaleString('en-IN')} · {inv.due_date ? `Due ${new Date(inv.due_date).toLocaleDateString('en-IN')}` : 'No due date'}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <Badge status={inv.status} />
              <button onClick={() => download(inv.id, inv.invoice_number)} className="text-gray-400 hover:text-gray-900">
                <Download size={16} />
              </button>
            </div>
          </div>
        ))}
        {invoices.length === 0 && (
          <div className="card p-12 text-center text-gray-400">No invoices yet</div>
        )}
      </div>
    </div>
  )
}