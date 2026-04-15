import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Download } from 'lucide-react'
import { PageHeader } from '../../components/ui/PageHeader'
import { Table } from '../../components/ui/Table'
import { Badge } from '../../components/ui/Badge'
import { Modal } from '../../components/ui/Modal'
import { payrollApi, operationsApi, clientApi } from '../../api/modules'

export default function OwnerFinancial() {
  const [tab, setTab] = useState('payroll')
  const [openPayroll, setOpenPayroll] = useState(false)
  const [openInvoice, setOpenInvoice] = useState(false)
  const [payrollForm, setPayrollForm] = useState({ period_month: new Date().getMonth() + 1, period_year: new Date().getFullYear() })
  const [invoiceForm, setInvoiceForm] = useState({ client_id: '', line_items: [{ description: '', quantity: 1, unit_price: 0 }], tax_percent: 18 })
  const qc = useQueryClient()

  const { data: runs = [] } = useQuery({ queryKey: ['payroll-runs'], queryFn: payrollApi.listRuns })
  const { data: invoices = [] } = useQuery({ queryKey: ['invoices'], queryFn: () => operationsApi.listInvoices() })
  const { data: clients = [] } = useQuery({ queryKey: ['clients'], queryFn: () => clientApi.list() })

  const createRun = useMutation({
    mutationFn: payrollApi.createRun,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['payroll-runs'] }); setOpenPayroll(false) },
  })

  const approveRun = useMutation({
    mutationFn: payrollApi.approveRun,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['payroll-runs'] }),
  })

  const createInvoice = useMutation({
    mutationFn: operationsApi.createInvoice,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['invoices'] }); setOpenInvoice(false) },
  })

  const downloadPayslip = async (runId) => {
    const run = await payrollApi.getRun(runId)
    // just show run detail — real download uses the payslip endpoint
    alert(`Payroll run has ${run.payslips?.length} payslips. Use individual payslip IDs to download PDFs.`)
  }

  const downloadInvoice = async (id) => {
    const res = await operationsApi.downloadInvoice(id)
    const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
    const a = document.createElement('a'); a.href = url; a.download = `invoice-${id.slice(0,8)}.pdf`; a.click()
  }

  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

  return (
    <div>
      <PageHeader title="Financial Control" />

      <div className="flex gap-1 mb-6 bg-gray-100 p-1 rounded-xl w-fit">
        {[['payroll','Payroll'],['invoices','Invoices']].map(([key,label]) => (
          <button key={key} onClick={() => setTab(key)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === key ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500 hover:text-gray-700'}`}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'payroll' && (
        <>
          <div className="flex justify-end mb-4">
            <button onClick={() => setOpenPayroll(true)} className="btn-primary flex items-center gap-2">
              <Plus size={16} /> Run Payroll
            </button>
          </div>
          <div className="card" style={{padding:0}}>
            <Table
              headers={['Period','Employees','Total Net','Status','']}
              rows={runs.map(r => [
                `${months[r.period_month-1]} ${r.period_year}`,
                r.total_employees,
                `₹${Number(r.total_net).toLocaleString('en-IN')}`,
                <Badge status={r.status} />,
                r.status === 'draft' ? (
                  <button onClick={() => approveRun.mutate(r.id)}
                    className="text-xs btn-primary py-1 px-3">
                    Approve & Generate PDFs
                  </button>
                ) : (
                  <button onClick={() => downloadPayslip(r.id)}
                    className="text-gray-500 hover:text-gray-900">
                    <Download size={15} />
                  </button>
                ),
              ])}
              empty="No payroll runs yet."
            />
          </div>
        </>
      )}

      {tab === 'invoices' && (
        <>
          <div className="flex justify-end mb-4">
            <button onClick={() => setOpenInvoice(true)} className="btn-primary flex items-center gap-2">
              <Plus size={16} /> New Invoice
            </button>
          </div>
          <div className="card" style={{padding:0}}>
            <Table
              headers={['Invoice #','Client','Total','Status','PDF']}
              rows={invoices.map(inv => [
                <span className="font-mono text-sm">{inv.invoice_number}</span>,
                inv.client_name,
                `₹${Number(inv.total_amount).toLocaleString('en-IN')}`,
                <Badge status={inv.status} />,
                <button onClick={() => downloadInvoice(inv.id)} className="text-gray-500 hover:text-gray-900">
                  <Download size={15} />
                </button>,
              ])}
              empty="No invoices yet."
            />
          </div>
        </>
      )}

      {/* Payroll Modal */}
      <Modal open={openPayroll} onClose={() => setOpenPayroll(false)} title="Run Payroll">
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Month</label>
              <select className="input" value={payrollForm.period_month}
                onChange={e => setPayrollForm(f => ({ ...f, period_month: +e.target.value }))}>
                {months.map((m,i) => <option key={i} value={i+1}>{m}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Year</label>
              <input type="number" className="input" value={payrollForm.period_year}
                onChange={e => setPayrollForm(f => ({ ...f, period_year: +e.target.value }))} />
            </div>
          </div>
          <p className="text-sm text-gray-500">
            This will calculate pay for all active employees based on attendance records.
          </p>
          <div className="flex gap-3 pt-2">
            <button onClick={() => setOpenPayroll(false)} className="btn-secondary flex-1">Cancel</button>
            <button onClick={() => createRun.mutate(payrollForm)} disabled={createRun.isPending} className="btn-primary flex-1">
              {createRun.isPending ? 'Calculating…' : 'Calculate Payroll'}
            </button>
          </div>
        </div>
      </Modal>

      {/* Invoice Modal */}
      <Modal open={openInvoice} onClose={() => setOpenInvoice(false)} title="Create Invoice" width="max-w-2xl">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Client</label>
            <select className="input" value={invoiceForm.client_id}
              onChange={e => setInvoiceForm(f => ({ ...f, client_id: e.target.value }))}>
              <option value="">Select client…</option>
              {clients.map(c => <option key={c.id} value={c.id}>{c.company_name}</option>)}
            </select>
          </div>
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-sm font-medium text-gray-700">Line Items</label>
              <button
                onClick={() => setInvoiceForm(f => ({ ...f, line_items: [...f.line_items, { description: '', quantity: 1, unit_price: 0 }] }))}
                className="text-xs text-brand-600 hover:underline"
              >
                + Add row
              </button>
            </div>
            <div className="space-y-2">
              {invoiceForm.line_items.map((item, i) => (
                <div key={i} className="grid grid-cols-12 gap-2">
                  <input className="input col-span-7" placeholder="Description"
                    value={item.description}
                    onChange={e => {
                      const items = [...invoiceForm.line_items]
                      items[i] = { ...items[i], description: e.target.value }
                      setInvoiceForm(f => ({ ...f, line_items: items }))
                    }} />
                  <input className="input col-span-2" type="number" placeholder="Qty"
                    value={item.quantity}
                    onChange={e => {
                      const items = [...invoiceForm.line_items]
                      items[i] = { ...items[i], quantity: +e.target.value }
                      setInvoiceForm(f => ({ ...f, line_items: items }))
                    }} />
                  <input className="input col-span-3" type="number" placeholder="Price ₹"
                    value={item.unit_price}
                    onChange={e => {
                      const items = [...invoiceForm.line_items]
                      items[i] = { ...items[i], unit_price: +e.target.value }
                      setInvoiceForm(f => ({ ...f, line_items: items }))
                    }} />
                </div>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">GST %</label>
            <input type="number" className="input" value={invoiceForm.tax_percent}
              onChange={e => setInvoiceForm(f => ({ ...f, tax_percent: +e.target.value }))} />
          </div>
          <div className="bg-gray-50 rounded-xl p-4">
            <div className="flex justify-between text-sm">
              <span className="text-gray-600">Subtotal</span>
              <span className="font-medium">₹{invoiceForm.line_items.reduce((s, i) => s + i.quantity * i.unit_price, 0).toLocaleString('en-IN')}</span>
            </div>
            <div className="flex justify-between text-sm mt-1">
              <span className="text-gray-600">GST ({invoiceForm.tax_percent}%)</span>
              <span className="font-medium">₹{(invoiceForm.line_items.reduce((s, i) => s + i.quantity * i.unit_price, 0) * invoiceForm.tax_percent / 100).toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
            </div>
            <div className="flex justify-between font-bold mt-2 pt-2 border-t border-gray-200">
              <span>Total</span>
              <span>₹{(invoiceForm.line_items.reduce((s, i) => s + i.quantity * i.unit_price, 0) * (1 + invoiceForm.tax_percent / 100)).toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
            </div>
          </div>
          <div className="flex gap-3 pt-2">
            <button onClick={() => setOpenInvoice(false)} className="btn-secondary flex-1">Cancel</button>
            <button onClick={() => createInvoice.mutate(invoiceForm)} disabled={createInvoice.isPending} className="btn-primary flex-1">
              {createInvoice.isPending ? 'Creating…' : 'Create & Send'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}