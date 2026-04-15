import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, X } from 'lucide-react'
import { PageHeader } from '../../components/ui/PageHeader'
import { Badge } from '../../components/ui/Badge'
import { Modal } from '../../components/ui/Modal'
import { contentApi } from '../../api/modules'

export default function ClientApprovals() {
  const [rejectModal, setRejectModal] = useState(null)
  const [feedback, setFeedback] = useState('')
  const qc = useQueryClient()

  const { data: approvals = [] } = useQuery({
    queryKey: ['client-approvals'],
    queryFn: () => contentApi.listApprovals({ status: 'all' }),
  })

  const approve = useMutation({
    mutationFn: (id) => contentApi.approve(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['client-approvals'] }),
  })

  const reject = useMutation({
    mutationFn: ({ id, feedback }) => contentApi.reject(id, feedback),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['client-approvals'] })
      setRejectModal(null)
      setFeedback('')
    },
  })

  return (
    <div>
      <PageHeader title="Content Approvals" />
      <div className="space-y-4">
        {approvals.map(a => (
          <div key={a.id} className="card p-6">
            <div className="flex items-start justify-between mb-4">
              <div>
                <p className="font-semibold text-gray-900">{a.brief_title}</p>
                <p className="text-sm text-gray-500">Angle: {a.draft_angle}</p>
              </div>
              <Badge status={a.status} />
            </div>
            <div className="bg-gray-50 rounded-xl p-4 mb-4">
              <p className="text-sm text-gray-700 whitespace-pre-wrap">{a.draft_body_preview}</p>
            </div>
            {a.status === 'pending' && (
              <div className="flex gap-3">
                <button
                  onClick={() => approve.mutate(a.id)}
                  disabled={approve.isPending}
                  className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-green-500 hover:bg-green-600 text-white rounded-xl font-medium transition-colors"
                >
                  <Check size={16} /> Approve
                </button>
                <button
                  onClick={() => setRejectModal(a)}
                  className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-red-50 hover:bg-red-100 text-red-600 rounded-xl font-medium transition-colors border border-red-200"
                >
                  <X size={16} /> Request Changes
                </button>
              </div>
            )}
            {a.status === 'rejected' && a.client_feedback && (
              <div className="bg-orange-50 border border-orange-200 rounded-lg px-4 py-3">
                <p className="text-xs font-semibold text-orange-700">Your feedback:</p>
                <p className="text-sm text-orange-600">{a.client_feedback}</p>
              </div>
            )}
          </div>
        ))}
        {approvals.length === 0 && (
          <div className="card p-12 text-center text-gray-400">No content to review</div>
        )}
      </div>

      <Modal open={!!rejectModal} onClose={() => setRejectModal(null)} title="Request Changes">
        <div className="space-y-4">
          <p className="text-sm text-gray-600">
            Tell us what you'd like changed for: <strong>{rejectModal?.brief_title}</strong>
          </p>
          <textarea
            className="input"
            rows={4}
            placeholder="What would you like us to change or improve?"
            value={feedback}
            onChange={e => setFeedback(e.target.value)}
          />
          <div className="flex gap-3">
            <button onClick={() => setRejectModal(null)} className="btn-secondary flex-1">Cancel</button>
            <button
              onClick={() => reject.mutate({ id: rejectModal.id, feedback })}
              disabled={!feedback || reject.isPending}
              className="flex-1 py-2.5 bg-red-500 hover:bg-red-600 text-white rounded-xl font-medium transition-colors"
            >
              {reject.isPending ? 'Sending…' : 'Send Feedback'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}