import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { MapPin, Clock, LogIn, LogOut } from 'lucide-react'
import { PageHeader } from '../../components/ui/PageHeader'
import { Badge } from '../../components/ui/Badge'
import { attendanceApi } from '../../api/modules'

export default function EmployeeAttendance() {
  const [gpsError, setGpsError] = useState('')
  const [loading, setLoading] = useState(false)
  const qc = useQueryClient()

  const { data: today } = useQuery({ queryKey: ['today-status'], queryFn: attendanceApi.today })
  const { data: sessions = [] } = useQuery({ queryKey: ['my-sessions'], queryFn: () => attendanceApi.mySessions() })

  const clockIn = async () => {
    setGpsError('')
    setLoading(true)
    try {
      const pos = await new Promise((res, rej) =>
        navigator.geolocation.getCurrentPosition(res, rej, { timeout: 10000 })
      )
      await attendanceApi.clockIn(pos.coords.latitude, pos.coords.longitude)
      qc.invalidateQueries({ queryKey: ['today-status'] })
      qc.invalidateQueries({ queryKey: ['my-sessions'] })
    } catch (e) {
      setGpsError(e.response?.data?.detail || e.message || 'Location access denied')
    } finally {
      setLoading(false)
    }
  }

  const clockOut = async () => {
    setLoading(true)
    try {
      await attendanceApi.clockOut()
      qc.invalidateQueries({ queryKey: ['today-status'] })
      qc.invalidateQueries({ queryKey: ['my-sessions'] })
    } finally {
      setLoading(false)
    }
  }

  const isIn = today?.is_clocked_in
  const session = today?.session

  return (
    <div>
      <PageHeader title="Attendance" />

      {/* Clock in/out card */}
      <div className={`card p-8 mb-6 text-center border-2 ${isIn ? 'border-green-400 bg-green-50/30' : 'border-gray-200'}`}>
        <div className={`w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-4 ${isIn ? 'bg-green-100' : 'bg-gray-100'}`}>
          <Clock size={36} className={isIn ? 'text-green-600' : 'text-gray-400'} />
        </div>
        <h2 className="text-2xl font-bold text-gray-900 mb-1">
          {isIn ? 'You are clocked in' : 'You are not clocked in'}
        </h2>
        {isIn && session && (
          <p className="text-gray-500 mb-1">
            Since {new Date(session.clock_in_time).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}
            {session.zone_name && ` · ${session.zone_name}`}
          </p>
        )}
        {gpsError && (
          <p className="text-red-600 text-sm mb-4 bg-red-50 rounded-lg px-4 py-2 mx-auto max-w-md">{gpsError}</p>
        )}
        <button
          onClick={isIn ? clockOut : clockIn}
          disabled={loading}
          className={`mt-4 px-8 py-3 rounded-xl font-semibold text-white transition-colors ${
            isIn
              ? 'bg-red-500 hover:bg-red-600'
              : 'bg-green-500 hover:bg-green-600'
          } disabled:opacity-50`}
        >
          {loading ? '…' : isIn ? (
            <span className="flex items-center gap-2"><LogOut size={18} /> Clock Out</span>
          ) : (
            <span className="flex items-center gap-2"><LogIn size={18} /> Clock In</span>
          )}
        </button>
        {!isIn && (
          <p className="text-xs text-gray-400 mt-3 flex items-center justify-center gap-1">
            <MapPin size={12} /> Your GPS location will be verified against approved zones
          </p>
        )}
      </div>

      {/* Session history */}
      <div className="card p-6">
        <h2 className="font-semibold text-gray-900 mb-4">This Month</h2>
        <div className="space-y-2">
          {sessions.map(s => (
            <div key={s.id} className="flex items-center justify-between py-2.5 border-b border-gray-100 last:border-0">
              <div>
                <p className="text-sm font-medium text-gray-900">
                  {new Date(s.clock_in_time).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' })}
                </p>
                <p className="text-xs text-gray-400">
                  {new Date(s.clock_in_time).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}
                  {s.clock_out_time && ` → ${new Date(s.clock_out_time).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}`}
                  {s.zone_name && ` · ${s.zone_name}`}
                </p>
              </div>
              <div className="text-right">
                <p className="font-semibold text-sm">{s.hours_worked ? `${s.hours_worked}h` : '—'}</p>
                <Badge status={s.status} />
              </div>
            </div>
          ))}
          {sessions.length === 0 && (
            <p className="text-gray-400 text-sm text-center py-6">No sessions this month</p>
          )}
        </div>
      </div>
    </div>
  )
}