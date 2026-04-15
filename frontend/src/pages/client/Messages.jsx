import { PageHeader } from '../../components/ui/PageHeader'

export default function ClientMessages() {
  return (
    <div>
      <PageHeader title="Messages" subtitle="Direct communication with your account team" />
      <div className="card p-12 text-center text-gray-400">
        Message thread view — send emails or WhatsApp messages through your account manager.
      </div>
    </div>
  )
}