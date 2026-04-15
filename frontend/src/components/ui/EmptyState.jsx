export function EmptyState({ icon: Icon, title, subtitle, action }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      {Icon && (
        <div className="p-4 bg-gray-100 rounded-2xl mb-4">
          <Icon size={28} className="text-gray-400" />
        </div>
      )}
      <p className="font-semibold text-gray-700">{title}</p>
      {subtitle && (
        <p className="text-sm text-gray-400 mt-1 max-w-xs">{subtitle}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}