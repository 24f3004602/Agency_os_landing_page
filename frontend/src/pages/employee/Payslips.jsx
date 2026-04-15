import { useQuery } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import { PageHeader } from '../../components/ui/PageHeader'
import { Badge } from '../../components/ui/Badge'
import { payrollApi } from '../../api/modules'

const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

export default function EmployeePayslips() {
  const { data: payslips = [] } = useQuery({
    queryKey: ['my-payslips'],
    queryFn: payrollApi.myPayslips,
  })

  const download = async (id, month, year) => {
    const res = await payrollApi.downloadPayslip(id)
    const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `payslip-${MONTHS[month-1]}-${year}.pdf`
    a.click()
  }

  return (
    <div>
      <PageHeader title="My Payslips" />
      <div className="space-y-3">
        {payslips.map(slip => (
          <div key={slip.id} className="card p-5 flex items-center justify-between">
            <div>
              <p className="font-semibold text-gray-900">
                {MONTHS[slip.period_month - 1]} {slip.period_year}
              </p>
              <p className="text-sm text-gray-500 mt-0.5">
                {slip.days_present} days · {slip.hours_worked}h worked
              </p>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-right">
                <p className="text-lg font-bold text-gray-900">
                  ₹{Number(slip.net_pay).toLocaleString('en-IN')}
                </p>
                <p className="text-xs text-gray-400">Net Pay</p>
              </div>
              {slip.has_pdf && (
                <button
                  onClick={() => download(slip.id, slip.period_month, slip.period_year)}
                  className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 hover:text-gray-900 transition-colors"
                  title="Download PDF"
                >
                  <Download size={18} />
                </button>
              )}
            </div>
          </div>
        ))}
        {payslips.length === 0 && (
          <div className="card p-12 text-center text-gray-400">
            No payslips yet. Payslips appear here after your owner approves each payroll run.
          </div>
        )}
      </div>
    </div>
  )
}