import { useEffect, useState } from 'react'
import { api, IpAddress, Subnet, IpStatus } from '../api/client'
import IpHistoryModal from '../components/IpHistoryModal'
import Pagination from '../components/Pagination'

const PAGE_SIZE = 25

const STATUS_BADGE: Record<IpStatus, string> = {
  free: 'bg-gray-800 text-white border border-gray-700',
  used: 'bg-sky-900/40 text-sky-300 border border-sky-700/40',
  reserved: 'bg-purple-900/40 text-purple-300 border border-purple-700/40',
  dhcp: 'bg-emerald-900/40 text-emerald-300 border border-emerald-700/40',
  static: 'bg-amber-900/40 text-amber-300 border border-amber-700/40',
  conflict: 'bg-red-900/40 text-red-300 border border-red-700/40',
}

export default function IpAddresses() {
  const [ips, setIps] = useState<IpAddress[]>([])
  const [subnets, setSubnets] = useState<Subnet[]>([])
  const [subnetId, setSubnetId] = useState('')
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [historyIp, setHistoryIp] = useState<string | null>(null)
  const [page, setPage] = useState(1)

  useEffect(() => { api.getSubnets().then(setSubnets).catch(() => {}) }, [])

  const load = (searchOverride?: string) => {
    setLoading(true)
    setPage(1)
    api.getIpAddresses({
      subnet_id: subnetId ? Number(subnetId) : undefined,
      status: status || undefined,
      search: (searchOverride ?? search) || undefined,
      limit: 500,
    }).then(setIps).catch(() => {}).finally(() => setLoading(false))
  }
  useEffect(load, [subnetId, status])

  const clearSearch = () => { setSearch(''); load('') }

  const subnetLabel = (id: number) => subnets.find(s => s.id === id)?.cidr ?? id

  const totalPages = Math.max(1, Math.ceil(ips.length / PAGE_SIZE))
  const pageClamped = Math.min(page, totalPages)
  const pagedIps = ips.slice((pageClamped - 1) * PAGE_SIZE, pageClamped * PAGE_SIZE)

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold text-white">IP Addresses</h1>

      <div className="flex items-center gap-3 flex-wrap">
        <select value={subnetId} onChange={e => setSubnetId(e.target.value)} className="bg-gray-800 border border-gray-700 text-white text-sm rounded-lg px-2 py-1.5">
          <option value="">All subnets</option>
          {subnets.map(s => <option key={s.id} value={s.id}>{s.cidr}</option>)}
        </select>
        <select value={status} onChange={e => setStatus(e.target.value)} className="bg-gray-800 border border-gray-700 text-white text-sm rounded-lg px-2 py-1.5">
          <option value="">All statuses</option>
          {(['free', 'used', 'reserved', 'dhcp', 'static', 'conflict'] as IpStatus[]).map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <div className="flex items-center gap-2">
          <input value={search} onChange={e => setSearch(e.target.value)} onKeyDown={e => e.key === 'Enter' && load()}
            placeholder="Search IP, hostname, MAC…"
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white placeholder-gray-600 w-64" />
          {search && <button onClick={clearSearch} className="text-xs text-white hover:text-white">✕</button>}
          <button onClick={() => load()} className="text-xs text-white border border-gray-700 rounded-lg px-3 py-1.5 hover:bg-gray-800">Search</button>
        </div>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-32 text-white text-sm">Loading…</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">IP</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Subnet</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Status</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Hostname</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">MAC</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Source</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Last Seen</th>
                <th className="text-right px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">History</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {pagedIps.map(ip => (
                <tr key={ip.id} className="hover:bg-gray-800/30">
                  <td className="px-5 py-3 font-mono text-white">{ip.ip_address}</td>
                  <td className="px-5 py-3 text-white font-mono">{subnetLabel(ip.subnet_id)}</td>
                  <td className="px-5 py-3"><span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_BADGE[ip.status]}`}>{ip.status}</span></td>
                  <td className="px-5 py-3 text-white">{ip.hostname ?? '—'}</td>
                  <td className="px-5 py-3 text-white font-mono">{ip.mac_address ?? '—'}</td>
                  <td className="px-5 py-3 text-white">{ip.source ?? '—'}</td>
                  <td className="px-5 py-3 text-white text-xs">{ip.last_seen ?? '—'}</td>
                  <td className="px-5 py-3 text-right">
                    {ip.has_history && (
                      <button onClick={() => setHistoryIp(ip.ip_address)} className="text-xs text-sky-400 hover:text-sky-300 underline">
                        History
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {ips.length === 0 && (
                <tr><td colSpan={8} className="px-5 py-8 text-center text-white">No IP addresses match this filter.</td></tr>
              )}
            </tbody>
          </table>
        )}
        {!loading && ips.length > 0 && (
          <div className="px-5 py-2 border-t border-gray-800 flex items-center justify-between text-xs text-white">
            <span>
              Showing {((pageClamped - 1) * PAGE_SIZE + 1).toLocaleString()}–{((pageClamped - 1) * PAGE_SIZE + pagedIps.length).toLocaleString()} of {ips.length.toLocaleString()} addresses
            </span>
            <Pagination page={pageClamped} totalPages={totalPages} onChange={setPage} />
          </div>
        )}
      </div>

      {historyIp && <IpHistoryModal ipAddress={historyIp} onClose={() => setHistoryIp(null)} />}
    </div>
  )
}
