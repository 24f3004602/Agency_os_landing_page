import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Clock } from 'lucide-react'
import { PageHeader } from '../../components/ui/PageHeader'
import { Table } from '../../components/ui/Table'
import { Badge } from '../../components/ui/Badge'
import { Modal } from '../../components/ui/Modal'
import { employeeApi, attendanceApi } from '../../api/modules'

export default function OwnerTeam() {
  const [tab, setTab] = useState('employees')
  const [openModal, setOpenModal] = useState(false)
  const [form, setForm] = useState({
    full_name: '', email: '', password: '',
    designation: '', compensation_type: 'fixed', compensation_rate: 0,
  })
  const qc = useQueryClient()

  const { data: employees = [] } = useQuery({
    queryKey: ['employees'],
    queryFn: () => employeeApi.list(),
  })
  const { data: teamAttendance = [] } = useQuery({
    queryKey: ['team-attendance'],
    queryFn: () => attendanceApi.team(),
  })

  const createEmp = useMutation({
    mutationFn: employeeApi.create,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['employees'] })
      setOpenModal(false)
    },
  })

  const todayDate = new Date().toISOString().split('T')[0]
  const { data: todayAttendance = [] } = useQuery({
    queryKey: ['today-attendance'],
    queryFn: () => attendanceApi.team({ date_filter: todayDate }),
  })

  return (
    <div>
      <PageHeader
        title="Team Command Centre"
        action={
          <button onClick={() => setOpenModal(true)} className="btn-primary flex items-center gap-2">
            <Plus size={16} /> Add Employee
          </button>
        }
      />

      {/* Tabs */}
      <div className="flex gap-1 mb-6 bg-gray-100 p-1 rounded-xl w-fit">
        {[['employees','Employees'],['attendance','Live Attendance']].map(([key,label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === key ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'employees' && (
        <div className="card" style={{padding:0}}>
          <Table
            headers={['Name', 'Email', 'Designation', 'Type', 'Rate', 'Status']}
            rows={employees.map(e => [
              <span className="font-medium">{e.full_name}</span>,
              <span className="text-gray-500 text-xs">{e.email}</span>,
              e.designation || '—',
              <span className="capitalize">{e.compensation_type}</span>,
              `₹${Number(e.compensation_rate).toLocaleString('en-IN')}`,
              <Badge status={e.is_active ? 'active' : 'inactive'} />,
            ])}
            empty="No employees yet. Add your first team member."
          />
        </div>
      )}

      {tab === 'attendance' && (
        <div className="space-y-3">
          {todayAttendance.map(emp => {
            const openSession = emp.sessions?.find(s => s.status === 'open')
            const isIn = !!openSession
            return (
              <div key={emp.employee_id} className="card p-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`w-3 h-3 rounded-full ${isIn ? 'bg-green-500' : 'bg-gray-300'}`} />
                  <div>
                    <p className="font-medium text-gray-900">{emp.employee_name}</p>
                    {openSession && (
                      <p className="text-xs text-gray-500 flex items-center gap-1 mt-0.5">
                        <Clock size={11} />
                        Clocked in at {new Date(openSession.clock_in_time).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}
                        {openSession.zone_name && ` — ${openSession.zone_name}`}
                      </p>
                    )}
                  </div>
                </div>
                <div>
                  <p className="text-sm text-gray-600">
                    {emp.total_hours_this_month}h this month
                  </p>
                  <Badge status={isIn ? 'active' : 'inactive'} label={isIn ? 'Clocked In' : 'Not In'} />
                </div>
              </div>
            )
          })}
          {todayAttendance.length === 0 && (
            <div className="card p-12 text-center text-gray-400">
              No attendance data for today
            </div>
          )}
        </div>
      )}

      <Modal open={openModal} onClose={() => setOpenModal(false)} title="Add Employee">
        <div className="space-y-4">
          {[
            ['Full Name', 'full_name', 'text'],
            ['Email', 'email', 'email'],
            ['Password', 'password', 'password'],
            ['Designation', 'designation', 'text'],
          ].map(([label, key, type]) => (
            <div key={key}>
              <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
              <input type={type} className="input" value={form[key]}
                onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} />
            </div>
          ))}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Compensation Type</label>
            <select className="input" value={form.compensation_type}
              onChange={e => setForm(f => ({ ...f, compensation_type: e.target.value }))}>
              <option value="fixed">Fixed Monthly</option>
              <option value="hourly">Hourly Rate</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {form.compensation_type === 'fixed' ? 'Monthly Salary (₹)' : 'Hourly Rate (₹)'}
            </label>
            <input type="number" className="input" value={form.compensation_rate}
              onChange={e => setForm(f => ({ ...f, compensation_rate: e.target.value }))} />
          </div>
          <div className="flex gap-3 pt-2">
            <button onClick={() => setOpenModal(false)} className="btn-secondary flex-1">Cancel</button>
            <button
              onClick={() => createEmp.mutate(form)}
              disabled={createEmp.isPending}
              className="btn-primary flex-1"
            >
              {createEmp.isPending ? 'Adding…' : 'Add Employee'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}