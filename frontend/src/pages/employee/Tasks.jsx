import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { PageHeader } from '../../components/ui/PageHeader'
import { Badge } from '../../components/ui/Badge'
import { taskApi } from '../../api/modules'

const STATUS_FLOW = { created: 'in_progress', in_progress: 'submitted', rejected: 'in_progress' }
const STATUS_LABEL = { created: 'Start Task', in_progress: 'Submit for Review', rejected: 'Resubmit' }

export default function EmployeeTasks() {
  const [filter, setFilter] = useState('all')
  const qc = useQueryClient()

  const { data: tasks = [] } = useQuery({
    queryKey: ['my-tasks'],
    queryFn: () => taskApi.myTasks(),
  })

  const updateStatus = useMutation({
    mutationFn: ({ id, status }) => taskApi.updateStatus(id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['my-tasks'] }),
  })

  const filtered = filter === 'all' ? tasks : tasks.filter(t => t.status === filter)

  const filters = [
    ['all', 'All'], ['created', 'New'], ['in_progress', 'In Progress'],
    ['submitted', 'Submitted'], ['rejected', 'Rejected'],
  ]

  return (
    <div>
      <PageHeader title="My Tasks" />

      <div className="flex gap-1 mb-6 bg-gray-100 p-1 rounded-xl w-fit flex-wrap">
        {filters.map(([key, label]) => (
          <button key={key} onClick={() => setFilter(key)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              filter === key ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500 hover:text-gray-700'
            }`}>
            {label}
          </button>
        ))}
      </div>

      <div className="space-y-3">
        {filtered.map(task => (
          <div key={task.id} className={`card p-5 border-l-4 ${
            task.status === 'overdue' ? 'border-l-red-400' :
            task.status === 'rejected' ? 'border-l-orange-400' :
            task.status === 'submitted' ? 'border-l-blue-400' :
            'border-l-gray-200'
          }`}>
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-gray-900">{task.title}</p>
                {task.description && (
                  <p className="text-sm text-gray-500 mt-1 line-clamp-2">{task.description}</p>
                )}
                {task.rejection_comment && (
                  <div className="mt-2 bg-orange-50 border border-orange-200 rounded-lg px-3 py-2">
                    <p className="text-xs font-semibold text-orange-700">Feedback:</p>
                    <p className="text-xs text-orange-600">{task.rejection_comment}</p>
                  </div>
                )}
                <div className="flex items-center gap-3 mt-3">
                  <Badge status={task.status} />
                  <Badge status={task.priority} label={`${task.priority} priority`} />
                  {task.deadline && (
                    <span className="text-xs text-gray-400">
                      Due: {new Date(task.deadline).toLocaleDateString('en-IN')}
                    </span>
                  )}
                </div>
              </div>
              {STATUS_FLOW[task.status] && (
                <button
                  onClick={() => updateStatus.mutate({ id: task.id, status: STATUS_FLOW[task.status] })}
                  disabled={updateStatus.isPending}
                  className="btn-primary text-sm flex-shrink-0"
                >
                  {STATUS_LABEL[task.status]}
                </button>
              )}
            </div>
          </div>
        ))}
        {filtered.length === 0 && (
          <div className="card p-12 text-center text-gray-400">
            No {filter === 'all' ? '' : filter} tasks
          </div>
        )}
      </div>
    </div>
  )
}