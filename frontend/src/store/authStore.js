import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/**
 * Auth store — persisted to localStorage.
 * Holds tokens + basic user info decoded from login response.
 */
const useAuthStore = create(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      role: null,          // superadmin | owner | employee | client
      userId: null,
      agencyId: null,
      fullName: null,
      activeModules: [],

      isAuthenticated: () => !!get().accessToken,

      setAuth: ({
        access_token,
        refresh_token,
        role,
        user_id,
        agency_id,
        full_name,
        active_modules,
      }) =>
        set((state) => ({
          accessToken: access_token,
          refreshToken: refresh_token,
          role,
          userId: user_id,
          agencyId: agency_id,
          fullName: full_name,
          activeModules: Array.isArray(active_modules)
            ? active_modules
            : state.activeModules,
        })),

      clearAuth: () =>
        set({
          accessToken: null,
          refreshToken: null,
          role: null,
          userId: null,
          agencyId: null,
          fullName: null,
          activeModules: [],
        }),
    }),
    {
      name: 'agencyos-auth',
      // Only persist tokens + identity — not derived state
      partialize: (s) => ({
        accessToken: s.accessToken,
        refreshToken: s.refreshToken,
        role: s.role,
        userId: s.userId,
        agencyId: s.agencyId,
        fullName: s.fullName,
        activeModules: s.activeModules,
      }),
    },
  ),
)

export default useAuthStore
