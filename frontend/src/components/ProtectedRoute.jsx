import { Navigate } from 'react-router-dom'
import useAuthStore from '../store/authStore'

/**
 * Wraps any route that requires authentication.
 * Optionally restricts to specific roles.
 *
 * Usage:
 *   <ProtectedRoute roles={['owner', 'superadmin']}>
 *     <OwnerDashboard />
 *   </ProtectedRoute>
 */
export default function ProtectedRoute({ children, roles = [], requiredModule = null }) {
  const { accessToken, role, activeModules } = useAuthStore()

  if (!accessToken) {
    return <Navigate to="/login" replace />
  }

  if (roles.length > 0 && !roles.includes(role)) {
    // Redirect to their own dashboard instead of showing 403
    const homeMap = {
      superadmin: '/superadmin',
      owner: '/owner',
      employee: '/employee',
      client: '/client',
    }
    return <Navigate to={homeMap[role] ?? '/login'} replace />
  }

  if (
    role === 'owner' &&
    requiredModule &&
    !(activeModules || []).includes(requiredModule)
  ) {
    return <Navigate to="/owner" replace />
  }

  return children
}
