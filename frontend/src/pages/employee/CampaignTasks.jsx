import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { PageHeader } from '../../components/ui/PageHeader'
import { Badge } from '../../components/ui/Badge'
import { Modal } from '../../components/ui/Modal'
import { campaignApi } from '../../api/modules'

const FLOW = { brief: 'in_progress', in_progress: 'draft', draft: 'review' }
const LABELS = { brief: 'Start', in_progress: 'Submit Draft', draft: 'Send for Review' }

export default function EmployeeCampaignTasks() {
  const [selectedTask, setSelectedTask] = useState(null)
  const [draft, setDraft] = useState('')
  const qc = useQueryClient()

  const { data: tasks = [] } = useQuery({
    queryKey: ['my-campaign-tasks'],
    queryFn: () => campaignApi.myTasks(),
  })

  const updateStatus = useMutation({
    mutationFn: ({ id, status, draft_content }) =>
      campaignApi.updateTaskStatus(id, { status, draft_content }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['my-campaign-tasks'] })
      setSelectedTask(null)
    },
  })

  const handleAdvance = (task) => {
    const nextStatus = FLOW[task.status]
    if (nextStatus === 'draft' || nextStatus === 'review') {
      setSelectedTask(task)
      setDraft(task.draft_content || '')
    } else if (nextStatus) {
      updateStatus.mutate({ id: task.id, status: nextStatus })
    }
  }

  return (
    <div>
      <PageHeader title="Campaign Tasks" subtitle="Content deliverables assigned to you" />
      <div className="space-y-3">
        {tasks.map(task => (
          <div key={task.id} className="card p-5">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <p className="text-xs text-gray-400 mb-1">{task.campaign_name}</p>
                <p className="font-semibold text-gray-900">{task.title}</p>
                <div className="flex items-center gap-2 mt-2">
                  <Badge status={task.content_type} label={task.content_type?.replace(/_/g,' ')} />
                  <Badge status={task.status} />
                </div>
                {task.feedback && (
                  <div className="mt-2 bg-orange-50 border border-orange-200 rounded-lg px-3 py-2">
                    <p className="text-xs font-semibold text-orange-700">Feedback:</p>
                    <p className="text-xs text-orange-600">{task.feedback}</p>
                  </div>
                )}
              </div>
              {FLOW[task.status] && (
                <button
                  onClick={() => handleAdvance(task)}
                  className="btn-primary text-sm flex-shrink-0"
                >
                  {LABELS[task.status]}
                </button>
              )}
            </div>
          </div>
        ))}
        {tasks.length === 0 && (
          <div className="card p-12 text-center text-gray-400">No campaign tasks assigned</div>
        )}
      </div>

      <Modal open={!!selectedTask} onClose={() => setSelectedTask(null)} title="Submit Draft Content" width="max-w-2xl">
        <div className="space-y-4">
          <p className="text-sm text-gray-600">
            Write your content for: <strong>{selectedTask?.title}</strong>
          </p>
          <textarea
            className="input"
            rows={10}
            placeholder="Write your draft content here…"
            value={draft}
            onChange={e => setDraft(e.target.value)}
          />
          <div className="flex gap-3 pt-2">
            <button onClick={() => setSelectedTask(null)} className="btn-secondary flex-1">Cancel</button>
            <button
              onClick={() => updateStatus.mutate({
                id: selectedTask.id,
                status: FLOW[selectedTask.status],
                draft_content: draft,
              })}
              disabled={!draft || updateStatus.isPending}
              className="btn-primary flex-1"
            >
              {updateStatus.isPending ? 'Submitting…' : 'Submit Draft'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}