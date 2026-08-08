import { useEffect, useState } from 'react'
import { api, DhcpLease } from '../api/client'
import IpHistoryModal from '../components/IpHistoryModal'
import Pagination from '../components/Pagination'
import HelpButton from '../components/HelpButton'

const PAGE_SIZE_OPTIONS = [25, 50, 75, 100]

const STATE_BADGE: Record<string, string> = {
  active: 'bg-emerald-900/40 text-emerald-300 border border-emerald-700/40',
  reserved: 'bg-purple-900/40 text-purple-300 border border-purple-700/40',
  expired: 'bg-gray-800 text-white border border-gray-700',
  released: 'bg-gray-800 text-white border border-gray-700',
}

export default function DhcpLeases() {
  const [leases, setLeases] = useState<DhcpLease[]>([])
  const [state, setState] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [historyIp, setHistoryIp] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)

  const load = (searchOverride?: string) => {
    setLoading(true)
    setPage(1)
    api.getDhcpLeases({ state: state || undefined, search: (searchOverride ?? search) || undefined, limit: 500 })
      .then(setLeases).catch(() => {}).finally(() => setLoading(false))
  }
  useEffect(load, [state])

  const clearSearch = () => { setSearch(''); load('') }

  const totalPages = Math.max(1, Math.ceil(leases.length / pageSize))
  const pageClamped = Math.min(page, totalPages)
  const pagedLeases = leases.slice((pageClamped - 1) * pageSize, pageClamped * pageSize)

  const changePageSize = (size: number) => {
    setPageSize(size)
    setPage(1)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h1 className="text-xl font-bold text-white">DHCP Leases</h1>
        <HelpButton title="DHCP Leases — How It Works">
          <p>Pulled directly from your DHCP collectors — <span className="text-gray-300 font-medium">Reserved</span> means a fixed/static mapping on the server, <span className="text-gray-300 font-medium">Active</span> is a live dynamic lease, and <span className="text-gray-300 font-medium">Expired</span>/<span className="text-gray-300 font-medium">Released</span> are no longer held by the client.</p>
          <p>Click the history icon on a row to see when that IP's assignment changed — first seen, changed, and released timestamps.</p>
        </HelpButton>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <select value={state} onChange={e => setState(e.target.value)} className="bg-gray-800 border border-gray-700 text-white text-sm rounded-lg px-2 py-1.5">
          <option value="">All states</option>
          <option value="active">Active</option>
          <option value="reserved">Reserved</option>
          <option value="expired">Expired</option>
          <option value="released">Released</option>
        </select>
        <div className="flex items-center gap-2">
          <input value={search} onChange={e => setSearch(e.target.value)} onKeyDown={e => e.key === 'Enter' && load()}
            placeholder="Search IP, hostname, MAC…"
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white placeholder-gray-600 w-64" />
          {search && <button onClick={clearSearch} className="text-xs text-white hover:text-white">✕</button>}
          <button onClick={() => load()} className="text-xs text-white border border-gray-700 rounded-lg px-3 py-1.5 hover:bg-gray-800">Search</button>
        </div>
      </div>

      {!loading && leases.length > 0 && (
        <div className="flex items-center justify-center gap-6">
          <Pagination page={pageClamped} totalPages={totalPages} onChange={setPage} />
          <div className="flex items-center gap-2">
            <label htmlFor="leases-per-page" className="text-xs text-gray-400">Leases per page:</label>
            <select
              id="leases-per-page"
              value={pageSize}
              onChange={e => changePageSize(Number(e.target.value))}
              className="text-sm bg-gray-800 border border-gray-700 text-white rounded-lg px-2 py-1 focus:outline-none focus:border-sky-500"
            >
              {PAGE_SIZE_OPTIONS.map(size => (
                <option key={size} value={size}>{size}</option>
              ))}
            </select>
          </div>
        </div>
      )}

      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-32 text-white text-sm">Loading…</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">IP</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">MAC</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Hostname</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">State</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Starts</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Ends</th>
                <th className="text-right px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">History</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {pagedLeases.map(l => (
                <tr key={l.id} className="hover:bg-gray-800/30">
                  <td className="px-5 py-3 font-mono text-white">{l.ip_address}</td>
                  <td className="px-5 py-3 font-mono text-white">{l.mac_address ?? '—'}</td>
                  <td className="px-5 py-3 text-white">{l.hostname ?? '—'}</td>
                  <td className="px-5 py-3"><span className={`px-2 py-0.5 rounded text-xs font-medium ${STATE_BADGE[l.state] ?? STATE_BADGE.expired}`}>{l.state}</span></td>
                  <td className="px-5 py-3 text-white text-xs">{l.starts_at ?? '—'}</td>
                  <td className="px-5 py-3 text-white text-xs">{l.ends_at ?? '—'}</td>
                  <td className="px-5 py-3 text-right">
                    {l.has_history && (
                      <button onClick={() => setHistoryIp(l.ip_address)} className="text-xs text-sky-400 hover:text-sky-300 underline">
                        History
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {leases.length === 0 && (
                <tr><td colSpan={7} className="px-5 py-8 text-center text-white">No leases yet — configure a DHCP collector under Collectors.</td></tr>
              )}
            </tbody>
          </table>
        )}
        {!loading && leases.length > 0 && (
          <div className="px-5 py-2 border-t border-gray-800 text-xs text-white">
            Showing {((pageClamped - 1) * pageSize + 1).toLocaleString()}–{((pageClamped - 1) * pageSize + pagedLeases.length).toLocaleString()} of {leases.length.toLocaleString()} leases
          </div>
        )}
      </div>

      {historyIp && <IpHistoryModal ipAddress={historyIp} onClose={() => setHistoryIp(null)} />}
    </div>
  )
}
