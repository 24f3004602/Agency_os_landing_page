import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { PageHeader } from '../../components/ui/PageHeader'
import { Badge } from '../../components/ui/Badge'
import { commApi } from '../../api/modules'

export default function OwnerCommunications() {
  const qc = useQueryClient()
  const { data: flags = [] } = useQuery({
    queryKey: ['comm-flags'],
    queryFn: () => commApi.flags({ reviewed: false }),
  })

  const review = useMutation({
    mutationFn: (id) => commApi.reviewFlag(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['comm-flags'] }),
  })

  const channelIcon = { email: '📧', whatsapp: '💬' }

  return (
    <div>
      <PageHeader title="Communication Flags" subtitle="AI-flagged messages requiring your review" />

      {flags.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-6">
          <p className="text-sm font-semibold text-red-800">
            {flags.length} unreviewed flag{flags.length !== 1 ? 's' : ''} require your attention
          </p>
        </div>
      )}

      <div className="space-y-4">
        {flags.map(log => (
          <div key={log.id} className="card p-5 border-l-4 border-l-red-400">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-3 mb-2">
                  <span>{channelIcon[log.channel]}</span>
                  <p className="font-medium text-gray-900">{log.employee_name}</p>
                  <span className="text-gray-400">→</span>
                  <p className="font-medium text-gray-900">{log.client_name}</p>
                  <Badge status="error" label={log.channel} />
                </div>
                {log.subject && (
                  <p className="text-xs text-gray-500 mb-1">Subject: {log.subject}</p>
                )}
                <p className="text-sm text-gray-700 bg-gray-50 rounded-lg p-3 mb-2 line-clamp-3">
                  {log.body}
                </p>
                {log.flag_reason && (
                  <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                    <p className="text-xs font-semibold text-red-700">Flag reason:</p>
                    <p className="text-xs text-red-600">{log.flag_reason}</p>
                  </div>
                )}
                <p className="text-xs text-gray-400 mt-2">
                  {new Date(log.created_at).toLocaleString('en-IN')}
                </p>
              </div>
              <button
                onClick={() => review.mutate(log.id)}
                disabled={review.isPending}
                className="btn-secondary text-sm flex-shrink-0"
              >
                Mark Reviewed
              </button>
            </div>
          </div>
        ))}
        {flags.length === 0 && (
          <div className="card p-12 text-center text-gray-400">
            No unreviewed flags. All communications are clean ✓
          </div>
        )}
      </div>
    </div>
  )
}