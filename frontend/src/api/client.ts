/**
 * pktIPAM API client — typed fetch wrappers.
 * Access token is stored in memory (not localStorage).
 */

let _accessToken: string | null = null
let _tokenRole: string | null = null

export function setToken(token: string, role: string) {
  _accessToken = token
  _tokenRole = role
}

export function clearToken() {
  _accessToken = null
  _tokenRole = null
}

export function getRole(): string | null {
  return _tokenRole
}

/**
 * Build a query string, omitting undefined/null values entirely.
 * `new URLSearchParams({foo: undefined})` does NOT omit `foo` — it
 * stringifies to the literal text "undefined", which a typed backend
 * query param (e.g. `subnet_id: int | None`) then fails to parse (422),
 * or a string param matches against literally, silently returning zero
 * rows instead of "no filter applied". Every optional-params GET must
 * build its query string through this helper, not the bare
 * `new URLSearchParams(params)` object-constructor form.
 */
function toQueryString(params?: Record<string, unknown>): string {
  if (!params) return ''
  const q = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) q.set(key, String(value))
  }
  const s = q.toString()
  return s ? `?${s}` : ''
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  if (_accessToken) headers['Authorization'] = `Bearer ${_accessToken}`

  const res = await fetch(`/api${path}`, { ...options, headers })

  if (res.status === 401) {
    const refreshed = await tryRefresh()
    if (refreshed) {
      headers['Authorization'] = `Bearer ${_accessToken}`
      const retry = await fetch(`/api${path}`, { ...options, headers })
      if (!retry.ok) throw new Error(`${retry.status} ${retry.statusText}`)
      return retry.status === 204 ? (null as T) : retry.json()
    }
    clearToken()
    window.location.href = '/login'
    throw new Error('Session expired')
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }

  if (res.status === 204) return null as T
  return res.json()
}

async function tryRefresh(): Promise<boolean> {
  try {
    const res = await fetch('/api/auth/refresh', { method: 'POST', credentials: 'include' })
    if (!res.ok) return false
    const data = await res.json()
    setToken(data.access_token, data.role)
    return true
  } catch {
    return false
  }
}

export const api = {
  // -- Auth --------------------------------------------------------------------
  // Deliberately bypasses request() — a bad password here is a normal login
  // failure, not an expired session, and must not trigger the 401 handler's
  // refresh-then-redirect-to-/login flow (that would hard-reload the login
  // page itself before the error message is even visible).
  login: async (username: string, password: string) => {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || res.statusText)
    }
    return res.json() as Promise<{ access_token: string; role: string }>
  },
  // Deliberately bypasses request() for the same reason as login() above.
  autoLogin: async () => {
    const res = await fetch('/api/auth/auto-login', { method: 'POST' })
    if (!res.ok) throw new Error('Auto-login not available')
    return res.json() as Promise<{ access_token: string; role: string }>
  },
  logout: () => request('/auth/logout', { method: 'POST' }),
  getAuthConfig: () => request<{ saml_enabled: boolean; local_enabled: boolean }>('/auth/config'),

  // -- Users ---------------------------------------------------------------------
  getMe: () => request<User>('/users/me'),
  getUsers: () => request<User[]>('/users'),
  createUser: (body: UserIn) =>
    request<User>('/users', { method: 'POST', body: JSON.stringify(body) }),
  updateUser: (id: number, body: Partial<UserIn> & { is_active?: boolean }) =>
    request<User>(`/users/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteUser: (id: number) => request(`/users/${id}`, { method: 'DELETE' }),
  setDefaultAdmin: (id: number) => request(`/users/${id}/set-default-admin`, { method: 'PATCH' }),
  resetUserPassword: (id: number, newPassword: string) =>
    request(`/users/${id}/reset-password`, { method: 'PATCH', body: JSON.stringify({ new_password: newPassword }) }),
  changeMyPassword: (current_password: string, new_password: string) =>
    request('/users/me/change-password', { method: 'POST', body: JSON.stringify({ current_password, new_password }) }),

  // -- Subnets ---------------------------------------------------------------------
  getSubnets: (params?: { site?: string }) => request<Subnet[]>(`/subnets${toQueryString(params)}`),
  getSubnet: (id: number) => request<Subnet>(`/subnets/${id}`),
  getSubnetUtilizationHistory: (id: number, sinceHours = 24) =>
    request<UtilizationPoint[]>(`/subnets/${id}/utilization-history?since_hours=${sinceHours}`),
  createSubnet: (body: Partial<Subnet>) => request<Subnet>('/subnets', { method: 'POST', body: JSON.stringify(body) }),
  updateSubnet: (id: number, body: Partial<Subnet>) => request<Subnet>(`/subnets/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteSubnet: (id: number) => request(`/subnets/${id}`, { method: 'DELETE' }),

  // -- Capacity planner --------------------------------------------------------------
  calculateCapacity: (hostCount: number, bufferPct = 0) =>
    request<CapacityCalculation>(`/capacity/calculate${toQueryString({ host_count: hostCount, buffer_pct: bufferPct })}`),
  searchCapacity: (params: { host_count: number; buffer_pct?: number; subnet_id?: number }) =>
    request<CapacitySearchResult>(`/capacity/search${toQueryString(params)}`),
  reserveCapacity: (body: CapacityReserveRequest) =>
    request<{ status: string; subnet_id: number; start_ip: string; end_ip: string; count: number }>(
      '/capacity/reserve', { method: 'POST', body: JSON.stringify(body) }
    ),

  // -- VLANs -----------------------------------------------------------------------
  getVlans: () => request<Vlan[]>('/vlans'),
  createVlan: (body: Partial<Vlan>) => request<Vlan>('/vlans', { method: 'POST', body: JSON.stringify(body) }),
  updateVlan: (id: number, body: Partial<Vlan>) => request<Vlan>(`/vlans/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteVlan: (id: number) => request(`/vlans/${id}`, { method: 'DELETE' }),

  // -- Sites -----------------------------------------------------------------------
  getSites: () => request<Site[]>('/sites'),
  createSite: (body: Partial<Site>) => request<Site>('/sites', { method: 'POST', body: JSON.stringify(body) }),
  updateSite: (id: number, body: Partial<Site>) => request<Site>(`/sites/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteSite: (id: number) => request(`/sites/${id}`, { method: 'DELETE' }),

  // -- SNMP Credentials --------------------------------------------------------------
  getSnmpCredentials: () => request<SnmpCredential[]>('/snmp-credentials'),
  createSnmpCredential: (body: SnmpCredentialInput) =>
    request<SnmpCredential>('/snmp-credentials', { method: 'POST', body: JSON.stringify(body) }),
  updateSnmpCredential: (id: number, body: Partial<SnmpCredentialInput>) =>
    request<SnmpCredential>(`/snmp-credentials/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteSnmpCredential: (id: number) => request(`/snmp-credentials/${id}`, { method: 'DELETE' }),

  // -- IP addresses ------------------------------------------------------------------
  getIpAddresses: (params?: { subnet_id?: number; status?: string; search?: string; limit?: number }) =>
    request<IpAddress[]>(`/ip-addresses${toQueryString(params)}`),
  getIpGrid: (subnetId: number) => request<IpAddress[]>(`/ip-addresses/grid/${subnetId}`),
  createManualIp: (body: Partial<IpAddress> & { subnet_id: number; ip_address: string }) =>
    request<IpAddress>('/ip-addresses', { method: 'POST', body: JSON.stringify(body) }),
  updateIpAddress: (id: number, body: Partial<IpAddress>) =>
    request<IpAddress>(`/ip-addresses/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteIpAddress: (id: number) => request(`/ip-addresses/${id}`, { method: 'DELETE' }),
  bulkUpdateIpAddresses: (body: BulkIpUpdate) =>
    request<{ status: string; updated: number }>('/ip-addresses/bulk-update', { method: 'POST', body: JSON.stringify(body) }),
  getIpAddressHistory: (params: { ip_address?: string; subnet_id?: number; limit?: number }) =>
    request<IpAddressHistoryEntry[]>(`/ip-address-history${toQueryString(params)}`),

  // -- DHCP leases / DNS records (read-only raw source data) -------------------------
  getDhcpLeases: (params?: { collector_id?: number; state?: string; search?: string; limit?: number }) =>
    request<DhcpLease[]>(`/dhcp-leases${toQueryString(params)}`),
  getDnsRecords: (params?: { collector_id?: number; record_type?: string; search?: string; limit?: number }) =>
    request<DnsRecord[]>(`/dns-records${toQueryString(params)}`),
  getRoutes: (params?: { collector_id?: number; protocol?: string; search?: string; limit?: number }) =>
    request<RouteEntry[]>(`/routes${toQueryString(params)}`),

  // -- Conflicts ---------------------------------------------------------------------
  getConflicts: (params?: { resolved?: boolean; acked?: boolean; conflict_type?: string; limit?: number }) => {
    const q = new URLSearchParams()
    if (params?.resolved !== undefined) q.set('resolved', String(params.resolved))
    if (params?.acked !== undefined) q.set('acked', String(params.acked))
    if (params?.conflict_type) q.set('conflict_type', params.conflict_type)
    if (params?.limit !== undefined) q.set('limit', String(params.limit))
    return request<Conflict[]>(`/conflicts?${q}`)
  },
  resolveConflict: (id: number) => request(`/conflicts/${id}/resolve`, { method: 'POST' }),
  resolveAllConflicts: () => request<{ status: string; resolved: number }>('/conflicts/resolve-all', { method: 'POST' }),
  resolveSelectedConflicts: (ids: number[]) =>
    request<{ status: string; resolved: number }>('/conflicts/resolve-selected', { method: 'POST', body: JSON.stringify({ ids }) }),
  ackConflict: (id: number) => request(`/conflicts/${id}/ack`, { method: 'POST' }),

  // -- Alerts ---------------------------------------------------------------------
  getAlertRules: () => request<AlertRule[]>('/alerts/rules'),
  createAlertRule: (body: Partial<AlertRule>) => request<AlertRule>('/alerts/rules', { method: 'POST', body: JSON.stringify(body) }),
  updateAlertRule: (id: number, body: Partial<AlertRule>) => request<AlertRule>(`/alerts/rules/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteAlertRule: (id: number) => request(`/alerts/rules/${id}`, { method: 'DELETE' }),
  toggleAlertRule: (id: number) => request<AlertRule>(`/alerts/rules/${id}/toggle`, { method: 'POST' }),
  exportAlertRules: async (): Promise<Blob> => {
    const headers: Record<string, string> = {}
    if (_accessToken) headers['Authorization'] = `Bearer ${_accessToken}`
    const res = await fetch('/api/alerts/rules/export', { headers })
    if (!res.ok) throw new Error(`Export failed: ${res.status} ${res.statusText}`)
    return res.blob()
  },
  importAlertRulesCsv: async (file: File): Promise<{ created: number; skipped: number; errors: string[] }> => {
    const formData = new FormData()
    formData.append('file', file)
    const headers: Record<string, string> = {}
    if (_accessToken) headers['Authorization'] = `Bearer ${_accessToken}`
    const res = await fetch('/api/alerts/rules/import-csv', { method: 'POST', headers, body: formData })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || res.statusText)
    }
    return res.json()
  },
  getAlertEvents: (params?: { active?: boolean; acked?: boolean; since?: string | null; until?: string | null; limit?: number }) => {
    const q = new URLSearchParams()
    if (params?.active !== undefined) q.set('active', String(params.active))
    if (params?.acked !== undefined) q.set('acked', String(params.acked))
    if (params?.since) q.set('since', params.since)
    if (params?.until) q.set('until', params.until)
    if (params?.limit !== undefined) q.set('limit', String(params.limit))
    return request<AlertEvent[]>(`/alerts/events?${q}`)
  },
  ackAlertEvent: (id: number) => request(`/alerts/events/${id}/ack`, { method: 'POST' }),
  ackAllAlertEvents: () => request<{ status: string; acked: number }>('/alerts/events/ack-all', { method: 'POST' }),
  resolveAlertEvent: (id: number) => request(`/alerts/events/${id}/resolve`, { method: 'POST' }),

  // -- Logs ---------------------------------------------------------------------
  getAppLogs: (params?: { level?: string; logger?: string; search?: string; since?: string | null; until?: string | null; limit?: number; offset?: number }) => {
    const q = new URLSearchParams()
    if (params?.level) q.set('level', params.level)
    if (params?.logger) q.set('logger', params.logger)
    if (params?.search) q.set('search', params.search)
    if (params?.since) q.set('since', params.since)
    if (params?.until) q.set('until', params.until)
    if (params?.limit !== undefined) q.set('limit', String(params.limit))
    if (params?.offset !== undefined) q.set('offset', String(params.offset))
    return request<{ total: number; limit: number; offset: number; records: AppLog[] }>(`/logs?${q}`)
  },
  getLogStats: () => request<LogStats>('/logs/stats'),
  clearLogs: () => request<{ status: string }>('/logs', { method: 'DELETE' }),
  setLogCaptureLevel: (level: string) => request<{ capture_level: string }>(`/logs/level?level=${level}`, { method: 'POST' }),

  // -- Collectors ---------------------------------------------------------------------
  getCollectorTypes: () => request<Record<string, CollectorType[]>>('/collectors/types'),
  getCollectors: (category?: string) => request<Collector[]>(`/collectors${category ? '?category=' + category : ''}`),
  getCollector: (id: number) => request<Collector & { config: Record<string, unknown> }>(`/collectors/${id}`),
  createCollector: (body: Partial<Collector> & { config: Record<string, unknown> }) =>
    request<Collector>('/collectors', { method: 'POST', body: JSON.stringify(body) }),
  updateCollector: (id: number, body: Partial<Collector> & { config?: Record<string, unknown> }) =>
    request<Collector>(`/collectors/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteCollector: (id: number) => request(`/collectors/${id}`, { method: 'DELETE' }),
  pollCollectorNow: (id: number) => request<{ status: string; rows: number }>(`/collectors/${id}/poll-now`, { method: 'POST' }),

  // -- Integrations (suite-token client of pktsnmp) -----------------------------------
  getIntegrations: () => request<Integration[]>('/integrations'),
  createIntegration: (body: IntegrationInput) =>
    request<Integration>('/integrations', { method: 'POST', body: JSON.stringify(body) }),
  updateIntegration: (id: number, body: Partial<IntegrationInput>) =>
    request<Integration>(`/integrations/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteIntegration: (id: number) => request(`/integrations/${id}`, { method: 'DELETE' }),
  testIntegration: (id: number) => request<{ healthy: boolean; detail: string }>(`/integrations/${id}/test`, { method: 'POST' }),

  // -- Suite (inbound — pktHub registering this app) --------------------------------
  getSuiteToken: () => request<{ suite_token: string; has_token: boolean }>('/suite/token'),
  regenerateSuiteToken: () => request<{ suite_token: string; status: string }>('/suite/regenerate', { method: 'POST' }),

  // -- Settings ---------------------------------------------------------------------
  aiChat: (question: string, context: Record<string, unknown> = {}) =>
    request<{ answer: string; provider?: string; tokens_used: number }>('/ai/chat', { method: 'POST', body: JSON.stringify({ question, context }) }),

  getSettings: () => request<Record<string, unknown>>('/settings'),
  updateSettings: (values: Record<string, unknown>) => request('/settings', { method: 'PUT', body: JSON.stringify({ values }) }),
  testNotification: (channel: string) =>
    request<{ status: string; detail?: string }>('/settings/test-notification', {
      method: 'POST',
      body: JSON.stringify({ channel }),
    }),

  // -- System ---------------------------------------------------------------------
  getSystemInfo: () =>
    request<{
      app_name: string; version: string; install_dir: string
      github: string; license: string; developer: string; contact: string
    }>('/system/info'),
  listBackups: () => request<Array<{ name: string; path: string; size_bytes: number; files: string[] }>>('/system/backups'),
  runBackupNow: () => request<{ status: string; path: string; files: string[]; kept: number }>('/system/backups/run', { method: 'POST' }),
  restartService: () => request<{ status: string; message: string }>('/system/restart', { method: 'POST' }),
  getPort: () => request<{ port: number }>('/system/port'),
  setPort: (port: number) =>
    request<{ port: number; message: string }>('/system/port', {
      method: 'POST',
      body: JSON.stringify({ port }),
    }),

  // ── Storage (SQLite-only — no backend picker like pktsnmp/pktflow) ─────────
  getStorageStats: () => request<StorageStats>('/system/storage-stats'),
  runCleanupNow: () => request<CleanupResult>('/system/cleanup', { method: 'POST' }),

  // ── Full backup bundle export/import ────────────────────────────────────
  exportConfig: async (): Promise<Blob> => {
    const headers: Record<string, string> = {}
    if (_accessToken) headers['Authorization'] = `Bearer ${_accessToken}`
    const res = await fetch('/api/system/export', { headers })
    if (!res.ok) throw new Error(`Export failed: ${res.status} ${res.statusText}`)
    return res.blob()
  },
  importBundle: async (file: File, files?: string[]): Promise<Record<string, string>> => {
    const formData = new FormData()
    formData.append('file', file)
    if (files) formData.append('files', files.join(','))
    const headers: Record<string, string> = {}
    if (_accessToken) headers['Authorization'] = `Bearer ${_accessToken}`
    const res = await fetch('/api/system/import', { method: 'POST', headers, body: formData })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || res.statusText)
    }
    return res.json()
  },
  restoreSnapshot: (name: string, files?: string[]): Promise<Record<string, string>> => {
    const qs = files && files.length ? `?files=${encodeURIComponent(files.join(','))}` : ''
    return request<Record<string, string>>(`/system/backups/restore/${encodeURIComponent(name)}${qs}`, { method: 'POST' })
  },

  // ── Documentation ─────────────────────────────────────────────────────────
  getDocs: () => request<{ slug: string; title: string }[]>('/docs-content'),
  getDoc: (slug: string) =>
    request<{ slug: string; title: string; content: string }>(`/docs-content/${slug}`),

  // ── SSL ───────────────────────────────────────────────────────────────────
  getSslStatus: () => request<SslStatus>('/system/ssl/status'),
  uploadSsl: async (cert: File, key: File): Promise<SslStatus> => {
    const formData = new FormData()
    formData.append('cert', cert)
    formData.append('key', key)
    const headers: Record<string, string> = {}
    if (_accessToken) headers['Authorization'] = `Bearer ${_accessToken}`
    const res = await fetch('/api/system/ssl/upload', { method: 'POST', headers, body: formData })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || res.statusText)
    }
    return res.json()
  },
  deleteSsl: () => request<SslStatus>('/system/ssl/cert', { method: 'DELETE' }),
  uploadSslPfx: async (pfx: File, passphrase: string): Promise<SslStatus> => {
    const formData = new FormData()
    formData.append('pfx', pfx)
    formData.append('passphrase', passphrase)
    const headers: Record<string, string> = {}
    if (_accessToken) headers['Authorization'] = `Bearer ${_accessToken}`
    const res = await fetch('/api/system/ssl/upload-pfx', { method: 'POST', headers, body: formData })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || res.statusText)
    }
    return res.json()
  },

  // ── User API Keys ────────────────────────────────────────────────────────
  getUserApiKeys: () => request<UserApiKey[]>('/user-api-keys'),
  setUserApiKey: (provider: string, api_key: string) =>
    request<UserApiKey>(`/user-api-keys/${provider}`, { method: 'PUT', body: JSON.stringify({ api_key }) }),
  testUserApiKey: (provider: string, api_key: string) =>
    request<{ status: string; detail: string }>(`/user-api-keys/${provider}/test`, { method: 'POST', body: JSON.stringify({ api_key }) }),
  setIpinfoFields: (enabled_fields: string[]) =>
    request<UserApiKey>('/user-api-keys/ipinfo/fields', { method: 'PUT', body: JSON.stringify({ enabled_fields }) }),
  setIpapiIsFields: (enabled_fields: string[]) =>
    request<UserApiKey>('/user-api-keys/ipapi_is/fields', { method: 'PUT', body: JSON.stringify({ enabled_fields }) }),
  setIpapiIsFreeTier: (free_tier: boolean) =>
    request<UserApiKey>('/user-api-keys/ipapi_is/free-tier', { method: 'PUT', body: JSON.stringify({ free_tier }) }),
  setMxtoolboxFields: (enabled_fields: string[]) =>
    request<UserApiKey>('/user-api-keys/mxtoolbox/fields', { method: 'PUT', body: JSON.stringify({ enabled_fields }) }),
  setProviderEnabled: (provider: string, enabled: boolean) =>
    request<UserApiKey>(`/user-api-keys/${provider}/enabled`, { method: 'PUT', body: JSON.stringify({ enabled }) }),
}

export interface UserApiKey {
  provider: string
  label: string
  api_key: string
  updated_at: string | null
  enabled_fields: string[] | null // ipinfo/ipapi_is/mxtoolbox only; null = not customized (all shown)
  free_tier: boolean // ipapi_is only — use its keyless free tier instead of api_key
  enabled: boolean // ipinfo/ipapi_is/abuseipdb/mxtoolbox only — show this provider's section in the IP Lookup modal at all
}

export interface StorageStats {
  db_size_bytes: number
  row_counts: Record<string, number>
}

export interface CleanupResult {
  status: string
  alert_events_deleted: number
  utilization_history_deleted: number
  alert_retention_days: number
  utilization_retention_days: number
}

export interface SslStatus {
  installed: boolean
  expires?: string
  expires_iso?: string
  days_until_expiry?: number
  subject?: string
  issuer?: string
  error?: string
  status?: string
}

// -- Types -----------------------------------------------------------------------

export interface UserIn {
  username: string
  email: string
  password?: string
  role: string
}

export interface User {
  id: number
  username: string
  email: string
  role: string
  is_active: boolean
  is_default_admin: boolean
  auth_provider: string
  created_at: string
  last_login: string | null
  has_password: boolean
}

export interface Subnet {
  id: number
  cidr: string
  vlan_id: number | null
  site: string | null
  description: string | null
  gateway: string | null
  parent_subnet_id: number | null
  computed_parent_id: number | null
  source: 'manual' | 'discovered'
  created_at: string
  updated_at: string
  utilization: { used_count: number; total_count: number; pct_used: number } | null
}

export interface UtilizationPoint {
  used_count: number
  total_count: number
  pct_used: number
  recorded_at: string
}

export interface Site {
  id: number
  name: string
  description: string | null
  created_at: string
}

export interface SnmpCredential {
  id: number
  name: string
  description: string
  snmp_version: 'v2c' | 'v3'
  community: string        // masked ("••••••••") in list/get responses
  security_name: string
  security_level: 'noAuthNoPriv' | 'authNoPriv' | 'authPriv'
  auth_protocol: 'SHA' | 'MD5'
  priv_protocol: 'AES' | 'DES'
  has_auth_key: boolean
  has_priv_key: boolean
  created_at: string
  updated_at: string
}

export interface SnmpCredentialInput {
  name: string
  description?: string
  snmp_version?: 'v2c' | 'v3'
  community?: string
  security_name?: string
  security_level?: 'noAuthNoPriv' | 'authNoPriv' | 'authPriv'
  auth_protocol?: 'SHA' | 'MD5'
  auth_key?: string
  priv_protocol?: 'AES' | 'DES'
  priv_key?: string
}

export interface CapacityCalculation {
  host_count: number
  buffer_pct: number
  required_hosts: number
  prefix: number
  block_size: number
  usable_hosts: number
}

export interface CapacityCandidate {
  subnet_id: number
  subnet_cidr: string
  cidr: string | null
  start_ip: string
  end_ip: string
  size: number
  aligned: boolean
}

export interface CapacitySearchResult extends CapacityCalculation {
  candidates: CapacityCandidate[]
}

export interface CapacityReserveRequest {
  subnet_id: number
  start_ip: string
  end_ip: string
  description?: string | null
  owner?: string | null
  tags?: string[]
}

export interface Vlan {
  id: number
  vlan_tag: number
  name: string
  site: string | null
  description: string | null
  created_at: string
}

export type IpStatus = 'free' | 'used' | 'reserved' | 'dhcp' | 'static' | 'conflict'

export interface IpAddress {
  id: number | null
  subnet_id: number
  ip_address: string
  status: IpStatus
  mac_address: string | null
  hostname: string | null
  dns_ptr: string | null
  description: string | null
  owner: string | null
  tags: string[]
  source: string | null
  last_seen: string | null
  created_at: string | null
  updated_at: string | null
  has_history?: boolean
}

export interface IpAddressHistoryEntry {
  id: number
  subnet_id: number
  ip_address: string
  event: 'first_seen' | 'changed' | 'released'
  status: string | null
  mac_address: string | null
  hostname: string | null
  source: string | null
  recorded_at: string
}

export interface BulkIpUpdate {
  subnet_id: number
  ip_addresses: string[]
  apply_status?: boolean
  status?: IpStatus | 'static' | 'reserved'
  apply_owner?: boolean
  owner?: string | null
  apply_description?: boolean
  description?: string | null
  apply_tags?: boolean
  tags?: string[]
}

export interface DhcpLease {
  id: number
  collector_id: number
  ip_address: string
  mac_address: string | null
  hostname: string | null
  client_id: string | null
  starts_at: string | null
  ends_at: string | null
  state: string
  last_seen: string
  has_history?: boolean
}

export interface DnsRecord {
  id: number
  collector_id: number
  zone: string
  name: string
  record_type: string
  value: string
  ttl: number | null
  last_seen: string
}

export interface RouteEntry {
  // One row per distinct (destination, next_hop) pair — device_label and
  // interface are comma-joined when more than one collector/device
  // confirms the same route, not a per-collector raw row (no id/
  // collector_id: a single logical route can be backed by several).
  device_label: string | null
  destination: string
  next_hop: string | null
  interface: string | null
  protocol: string | null
  metric: number | null
  last_seen: string
  // Not SNMP-observed routing data — the subnet's admin-configured gateway
  // (Subnets page), surfaced only as a fallback for display when next_hop
  // is null (a directly-connected/"local" route has no real next-hop in
  // any protocol). Always render distinctly from next_hop, never merged
  // in as if it were the same kind of data.
  subnet_gateway: string | null
}

export type ConflictType = 'duplicate_ip' | 'duplicate_mac' | 'static_dhcp_mismatch' | 'dns_mismatch' | 'subnet_overlap' | 'subnet_unrouted' | 'route_gateway_mismatch'

export interface Conflict {
  id: number
  conflict_type: ConflictType
  ip_address: string | null
  subnet_id: number | null
  details: Record<string, unknown>
  detected_at: string
  resolved_at: string | null
  resolved_by: string | null
  acked: boolean
  acked_by: string | null
  acked_at: string | null
}

export type AlertConditionType = 'subnet_near_exhaustion' | 'ip_conflict_detected' | 'dhcp_pool_exhausted' | 'dns_ptr_mismatch' | 'collector_down'

export interface AlertRule {
  id: number
  name: string
  condition_type: AlertConditionType
  threshold: number | null
  severity: 'info' | 'warning' | 'critical'
  enabled: boolean
  cooldown_min: number
  channels: string[]
  created_at: string
}

export interface AlertEvent {
  id: number
  rule_id: number | null
  subnet_id: number | null
  ip_address: string | null
  severity: string
  message: string
  value: number | null
  threshold: number | null
  active: boolean
  acked: boolean
  acked_by: string | null
  acked_at: string | null
  resolved: boolean
  auto_resolved: boolean
  resolved_at: string | null
  created_at: string
}

export interface AppLog {
  id: number
  level: string
  logger: string
  message: string
  exc_info: string | null
  created_at: string
}

export interface LogStats {
  total: number
  by_level: Record<string, number>
  loggers: string[]
  latest_ts: string | null
  capture_level: string
}

export type CollectorCategory = 'dhcp' | 'dns' | 'device'

export type FieldType = 'text' | 'password' | 'number' | 'toggle' | 'select' | 'multiselect' | 'string_list' | 'host_list' | 'site_select' | 'credential_select' | 'pktsnmp_select'

export interface FieldOption {
  value: string
  label: string
}

export interface FieldShowIf {
  key: string
  equals: string
}

export interface FieldSchema {
  key: string
  label: string
  type: FieldType
  required?: boolean
  placeholder?: string
  help?: string
  default?: unknown
  options?: FieldOption[]        // select | multiselect
  sub_fields?: FieldSchema[]     // host_list — columns per row
  item_placeholder?: string      // string_list
  show_if?: FieldShowIf          // only render when another field in the same form equals a value
}

export interface CollectorType {
  type: string
  label: string
  implemented: boolean
  fields: FieldSchema[]
}

export interface Collector {
  id: number
  name: string
  category: CollectorCategory
  collector_type: string
  poll_interval_sec: number
  enabled: boolean
  status: string
  last_poll_at: string | null
  last_error: string | null
  created_at: string
}

export interface Integration {
  id: number
  name: string
  app_name: string
  base_url: string
  has_token: boolean
  enabled: boolean
  health_status: string
  last_health_check: string | null
}

export interface IntegrationInput {
  name: string
  app_name?: string
  base_url: string
  suite_token: string
  enabled?: boolean
}
