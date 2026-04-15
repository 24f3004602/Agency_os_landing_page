import { clsx } from 'clsx'

const variants = {
  active:       'badge-green',
  success:      'badge-green',
  verified:     'badge-green',
  complete:     'badge-green',
  approved:     'badge-green',
  published:    'badge-green',
  won:          'badge-green',
  warning:      'badge-amber',
  at_risk:      'badge-amber',
  pending:      'badge-amber',
  draft:        'badge-amber',
  in_progress:  'badge-amber',
  trial:        'badge-amber',
  error:        'badge-red',
  failed:       'badge-red',
  overdue:      'badge-red',
  critical:     'badge-red',
  churned:      'badge-red',
  rejected:     'badge-red',
  lost:         'badge-red',
  default:      'badge-gray',
  inactive:     'badge-gray',
  paused:       'badge-gray',
  info:         'badge-blue',
  engaged:      'badge-blue',
  proposal:     'badge-blue',
}

export function Badge({ status, label, className }) {
  const key = status?.toLowerCase().replace(/\s+/g, '_')
  const cls = variants[key] || 'badge-gray'
  return (
    <span className={clsx(cls, className)}>
      {label || status}
    </span>
  )
}