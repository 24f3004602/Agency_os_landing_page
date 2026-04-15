import api from './client'

// ── Auth ─────────────────────────────────────────────────────────────────────
export const authApi = {
  login: (email, password) =>
    api.post('/auth/login', { email, password }).then(r => r.data),
  refresh: (refresh_token) =>
    api.post('/auth/refresh', { refresh_token }).then(r => r.data),
}

// ── SuperAdmin ────────────────────────────────────────────────────────────────
export const superadminApi = {
  createAgency: (body) =>
    api.post('/superadmin/agencies', body).then(r => r.data),
  listAgencies: () =>
    api.get('/superadmin/agencies').then(r => r.data),
}

// ── Employees ─────────────────────────────────────────────────────────────────
export const employeeApi = {
  create: (body) => api.post('/employees', body).then(r => r.data),
  list: (includeInactive = false) =>
    api.get('/employees', { params: { include_inactive: includeInactive } }).then(r => r.data),
  get: (id) => api.get(`/employees/${id}`).then(r => r.data),
  update: (id, body) => api.put(`/employees/${id}`, body).then(r => r.data),
  deactivate: (id) => api.delete(`/employees/${id}`),
  me: () => api.get('/employees/me').then(r => r.data),
}

// ── Clients ───────────────────────────────────────────────────────────────────
export const clientApi = {
  create: (body) => api.post('/clients', body).then(r => r.data),
  list: (params = {}) => api.get('/clients', { params }).then(r => r.data),
  get: (id) => api.get(`/clients/${id}`).then(r => r.data),
  update: (id, body) => api.put(`/clients/${id}`, body).then(r => r.data),
}

// ── Attendance ────────────────────────────────────────────────────────────────
export const attendanceApi = {
  clockIn: (latitude, longitude) =>
    api.post('/attendance/clock-in', { latitude, longitude }).then(r => r.data),
  clockOut: () => api.post('/attendance/clock-out').then(r => r.data),
  today: () => api.get('/attendance/today').then(r => r.data),
  mySessions: (params = {}) =>
    api.get('/attendance/my-sessions', { params }).then(r => r.data),
  team: (params = {}) =>
    api.get('/attendance/team', { params }).then(r => r.data),
}

// ── Geofence ──────────────────────────────────────────────────────────────────
export const geofenceApi = {
  createZone: (body) => api.post('/geofence/zones', body).then(r => r.data),
  listZones: () => api.get('/geofence/zones').then(r => r.data),
  updateZone: (id, body) => api.put(`/geofence/zones/${id}`, body).then(r => r.data),
  deleteZone: (id) => api.delete(`/geofence/zones/${id}`),
}

// ── M1 Tasks ──────────────────────────────────────────────────────────────────
export const taskApi = {
  create: (body) => api.post('/tasks', body).then(r => r.data),
  list: (params = {}) => api.get('/tasks', { params }).then(r => r.data),
  myTasks: (params = {}) => api.get('/tasks/my', { params }).then(r => r.data),
  get: (id) => api.get(`/tasks/${id}`).then(r => r.data),
  updateStatus: (id, status) =>
    api.patch(`/tasks/${id}/status`, { status }).then(r => r.data),
  verify: (id, action, comment) =>
    api.patch(`/tasks/${id}/verify`, { action, comment }).then(r => r.data),
  delete: (id) => api.delete(`/tasks/${id}`),
}

// ── Payroll ───────────────────────────────────────────────────────────────────
export const payrollApi = {
  createRun: (body) => api.post('/payroll/runs', body).then(r => r.data),
  listRuns: () => api.get('/payroll/runs').then(r => r.data),
  getRun: (id) => api.get(`/payroll/runs/${id}`).then(r => r.data),
  approveRun: (id) => api.post(`/payroll/runs/${id}/approve`).then(r => r.data),
  myPayslips: () => api.get('/payroll/payslips/my').then(r => r.data),
  downloadPayslip: (id) =>
    api.get(`/payroll/payslips/${id}/pdf`, { responseType: 'blob' }),
}

// ── Communications ────────────────────────────────────────────────────────────
export const commApi = {
  sendEmail: (body) => api.post('/communications/send/email', body).then(r => r.data),
  sendWhatsApp: (body) => api.post('/communications/send/whatsapp', body).then(r => r.data),
  thread: (clientId, params = {}) =>
    api.get(`/communications/thread/${clientId}`, { params }).then(r => r.data),
  flags: (params = {}) => api.get('/communications/flags', { params }).then(r => r.data),
  reviewFlag: (id, notes) =>
    api.patch(`/communications/flags/${id}/review`, { notes }).then(r => r.data),
}

// ── M2 Operations ─────────────────────────────────────────────────────────────
export const operationsApi = {
  triggerOnboarding: (body) =>
    api.post('/m2/onboarding/trigger', body).then(r => r.data),
  getOnboarding: (clientId) =>
    api.get(`/m2/onboarding/${clientId}`).then(r => r.data),
  createInvoice: (body) => api.post('/m2/invoices', body).then(r => r.data),
  listInvoices: (params = {}) =>
    api.get('/m2/invoices', { params }).then(r => r.data),
  getInvoice: (id) => api.get(`/m2/invoices/${id}`).then(r => r.data),
  updateInvoiceStatus: (id, status) =>
    api.patch(`/m2/invoices/${id}/status`, { status }).then(r => r.data),
  downloadInvoice: (id) =>
    api.get(`/m2/invoices/${id}/pdf`, { responseType: 'blob' }),
}

// ── M3 Reporting ──────────────────────────────────────────────────────────────
export const reportingApi = {
  setConfig: (clientId, body) =>
    api.post(`/m3/config/${clientId}`, body).then(r => r.data),
  getConfig: (clientId) =>
    api.get(`/m3/config/${clientId}`).then(r => r.data),
  generate: (body) => api.post('/m3/reports/generate', body).then(r => r.data),
  list: (params = {}) => api.get('/m3/reports', { params }).then(r => r.data),
  get: (id) => api.get(`/m3/reports/${id}`).then(r => r.data),
  downloadPdf: (id) =>
    api.get(`/m3/reports/${id}/pdf`, { responseType: 'blob' }),
}

// ── M4 Churn ──────────────────────────────────────────────────────────────────
export const churnApi = {
  listAlerts: (params = {}) => api.get('/m4/alerts', { params }).then(r => r.data),
  getAlert: (id) => api.get(`/m4/alerts/${id}`).then(r => r.data),
  resolveAlert: (id, body) =>
    api.patch(`/m4/alerts/${id}/resolve`, body).then(r => r.data),
  riskScores: () => api.get('/m4/risk-scores').then(r => r.data),
  scan: (clientId) =>
    api.post('/m4/scan', null, { params: clientId ? { client_id: clientId } : {} })
      .then(r => r.data),
}

// ── M5 Campaigns ──────────────────────────────────────────────────────────────
export const campaignApi = {
  create: (body) => api.post('/m5/campaigns', body).then(r => r.data),
  list: (params = {}) => api.get('/m5/campaigns', { params }).then(r => r.data),
  get: (id) => api.get(`/m5/campaigns/${id}`).then(r => r.data),
  update: (id, body) => api.put(`/m5/campaigns/${id}`, body).then(r => r.data),
  createTask: (campaignId, body) =>
    api.post(`/m5/campaigns/${campaignId}/tasks`, body).then(r => r.data),
  getTasks: (campaignId, params = {}) =>
    api.get(`/m5/campaigns/${campaignId}/tasks`, { params }).then(r => r.data),
  getTask: (id) => api.get(`/m5/tasks/${id}`).then(r => r.data),
  updateTaskStatus: (id, body) =>
    api.patch(`/m5/tasks/${id}/status`, body).then(r => r.data),
  approveTask: (id, body) =>
    api.post(`/m5/tasks/${id}/approve`, body).then(r => r.data),
  rejectTask: (id, feedback) =>
    api.post(`/m5/tasks/${id}/reject`, { feedback }).then(r => r.data),
  myTasks: (params = {}) =>
    api.get('/m5/tasks/my', { params }).then(r => r.data),
}

// ── M6 Research ───────────────────────────────────────────────────────────────
export const researchApi = {
  addCompetitor: (body) => api.post('/m6/competitors', body).then(r => r.data),
  listCompetitors: (clientId) =>
    api.get(`/m6/competitors/${clientId}`).then(r => r.data),
  removeCompetitor: (id) => api.delete(`/m6/competitors/${id}`),
  runResearch: (body) => api.post('/m6/research/run', body).then(r => r.data),
  listBriefs: (params = {}) =>
    api.get('/m6/research/briefs', { params }).then(r => r.data),
  getBrief: (id) => api.get(`/m6/research/briefs/${id}`).then(r => r.data),
  markActedOn: (id) =>
    api.patch(`/m6/research/briefs/${id}/act`).then(r => r.data),
  search: (query, clientId) =>
    api.get('/m6/research/search', {
      params: { query, ...(clientId ? { client_id: clientId } : {}) }
    }).then(r => r.data),
}

// ── M7 Leads ──────────────────────────────────────────────────────────────────
export const leadsApi = {
  upsertIcp: (body) => api.post('/m7/icp', body).then(r => r.data),
  getIcp: () => api.get('/m7/icp').then(r => r.data),
  createLead: (body) => api.post('/m7/leads', body).then(r => r.data),
  listLeads: (params = {}) => api.get('/m7/leads', { params }).then(r => r.data),
  getLead: (id) => api.get(`/m7/leads/${id}`).then(r => r.data),
  rescore: (id) => api.post(`/m7/leads/${id}/score`).then(r => r.data),
  updateStatus: (id, status) =>
    api.patch(`/m7/leads/${id}/status`, { status }).then(r => r.data),
}

// ── M8 Outreach ───────────────────────────────────────────────────────────────
export const outreachApi = {
  createSequence: (body) =>
    api.post('/m8/sequences', body).then(r => r.data),
  listSequences: (params = {}) =>
    api.get('/m8/sequences', { params }).then(r => r.data),
  getSequence: (id) => api.get(`/m8/sequences/${id}`).then(r => r.data),
  getSteps: (id) =>
    api.get(`/m8/sequences/${id}/steps`).then(r => r.data),
  approveStep: (sequenceId, stepId) =>
    api.post(`/m8/sequences/${sequenceId}/approve-step`, { step_id: stepId })
      .then(r => r.data),
  sendNext: (id) =>
    api.post(`/m8/sequences/${id}/send-next`).then(r => r.data),
  pause: (id) => api.patch(`/m8/sequences/${id}/pause`).then(r => r.data),
  resume: (id) => api.patch(`/m8/sequences/${id}/resume`).then(r => r.data),
}

// ── M9 ABM ────────────────────────────────────────────────────────────────────
export const abmApi = {
  createAccount: (body) => api.post('/m9/accounts', body).then(r => r.data),
  listAccounts: (params = {}) =>
    api.get('/m9/accounts', { params }).then(r => r.data),
  getAccount: (id) => api.get(`/m9/accounts/${id}`).then(r => r.data),
  updateStage: (id, body) =>
    api.patch(`/m9/accounts/${id}/stage`, body).then(r => r.data),
  orchestrate: (id) =>
    api.post(`/m9/accounts/${id}/orchestrate`).then(r => r.data),
  logTouch: (id, body) =>
    api.post(`/m9/accounts/${id}/touches`, body).then(r => r.data),
  addNote: (id, content) =>
    api.post(`/m9/accounts/${id}/notes`, { content }).then(r => r.data),
  feed: () => api.get('/m9/feed').then(r => r.data),
}

// ── M10 Optimisation ──────────────────────────────────────────────────────────
export const optimisationApi = {
  upsertConfig: (clientId, body) =>
    api.post(`/m10/config/${clientId}`, body).then(r => r.data),
  getConfig: (clientId) =>
    api.get(`/m10/config/${clientId}`).then(r => r.data),
  toggleKillSwitch: (clientId) =>
    api.patch(`/m10/config/${clientId}/kill-switch`).then(r => r.data),
  triggerRun: (clientId) =>
    api.post('/m10/runs', { client_id: clientId }).then(r => r.data),
  listRuns: (params = {}) =>
    api.get('/m10/runs', { params }).then(r => r.data),
  getRun: (id) => api.get(`/m10/runs/${id}`).then(r => r.data),
  approveRecs: (runId, recommendationIds) =>
    api.post(`/m10/runs/${runId}/approve`, {
      recommendation_ids: recommendationIds
    }).then(r => r.data),
  listAlerts: (params = {}) =>
    api.get('/m10/alerts', { params }).then(r => r.data),
  acknowledgeAlert: (id) =>
    api.patch(`/m10/alerts/${id}/acknowledge`).then(r => r.data),
}

// ── M11 Content ───────────────────────────────────────────────────────────────
export const contentApi = {
  createBrief: (body) => api.post('/m11/briefs', body).then(r => r.data),
  listBriefs: (params = {}) =>
    api.get('/m11/briefs', { params }).then(r => r.data),
  getBrief: (id) => api.get(`/m11/briefs/${id}`).then(r => r.data),
  generate: (id) =>
    api.post(`/m11/briefs/${id}/generate`).then(r => r.data),
  getDraft: (id) => api.get(`/m11/drafts/${id}`).then(r => r.data),
  submitForApproval: (body) =>
    api.post('/m11/approvals/submit', body).then(r => r.data),
  listApprovals: (params = {}) =>
    api.get('/m11/approvals', { params }).then(r => r.data),
  approve: (id, feedback) =>
    api.post(`/m11/approvals/${id}/approve`, { feedback }).then(r => r.data),
  reject: (id, feedback) =>
    api.post(`/m11/approvals/${id}/reject`, { feedback }).then(r => r.data),
  pipeline: (clientId) =>
    api.get(`/m11/pipeline/${clientId}`).then(r => r.data),
}