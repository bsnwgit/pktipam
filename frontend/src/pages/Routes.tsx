import { useEffect, useState } from 'react'
import { api, RouteEntry } from '../api/client'
import Pagination from '../components/Pagination'

const PAGE_SIZE_OPTIONS = [25, 50, 75, 100]

const PROTOCOL_BADGE: Record<string, string> = {
  local: 'bg-emerald-900/40 text-emerald-300 border border-emerald-700/40',
  static: 'bg-sky-900/40 text-sky-300 border border-sky-700/40',
  ospf: 'bg-purple-900/40 text-purple-300 border border-purple-700/40',
  bgp: 'bg-purple-900/40 text-purple-300 border border-purple-700/40',
  eigrp: 'bg-purple-900/40 text-purple-300 border border-purple-700/40',
  rip: 'bg-amber-900/40 text-amber-300 border border-amber-700/40',
}

export default function Routes() {
  const [routes, setRoutes] = useState<RouteEntry[]>([])
  const [protocol, setProtocol] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)

  const load = (searchOverride?: string) => {
    setLoading(true)
    setPage(1)
    api.getRoutes({ protocol: protocol || undefined, search: (searchOverride ?? search) || undefined, limit: 1000 })
      .then(setRoutes).catch(() => {}).finally(() => setLoading(false))
  }
  useEffect(load, [protocol])

  const clearSearch = () => { setSearch(''); load('') }

  const totalPages = Math.max(1, Math.ceil(routes.length / pageSize))
  const pageClamped = Math.min(page, totalPages)
  const pagedRoutes = routes.slice((pageClamped - 1) * pageSize, pageClamped * pageSize)

  const changePageSize = (size: number) => {
    setPageSize(size)
    setPage(1)
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold text-white">Routing Tables</h1>

      <div className="flex items-center gap-3 flex-wrap">
        <select value={protocol} onChange={e => setProtocol(e.target.value)} className="bg-gray-800 border border-gray-700 text-white text-sm rounded-lg px-2 py-1.5">
          <option value="">All protocols</option>
          <option value="local">Local</option>
          <option value="static">Static</option>
          <option value="ospf">OSPF</option>
          <option value="bgp">BGP</option>
          <option value="eigrp">EIGRP</option>
          <option value="rip">RIP</option>
          <option value="other">Other</option>
        </select>
        <div className="flex items-center gap-2">
          <input value={search} onChange={e => setSearch(e.target.value)} onKeyDown={e => e.key === 'Enter' && load()}
            placeholder="Search destination, next hop, device…"
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white placeholder-gray-600 w-72" />
          {search && <button onClick={clearSearch} className="text-xs text-white hover:text-white">✕</button>}
          <button onClick={() => load()} className="text-xs text-white border border-gray-700 rounded-lg px-3 py-1.5 hover:bg-gray-800">Search</button>
        </div>
      </div>

      {!loading && routes.length > 0 && (
        <div className="flex items-center justify-center gap-6">
          <Pagination page={pageClamped} totalPages={totalPages} onChange={setPage} />
          <div className="flex items-center gap-2">
            <label htmlFor="routes-per-page" className="text-xs text-gray-400">Routes per page:</label>
            <select
              id="routes-per-page"
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
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Destination</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Next Hop</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Interface</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Protocol</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Metric</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Device</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Last Seen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {pagedRoutes.map(r => (
                <tr key={`${r.destination}|${r.next_hop ?? ''}`} className="hover:bg-gray-800/30">
                  <td className="px-5 py-3 font-mono text-white">{r.destination}</td>
                  <td className="px-5 py-3 font-mono text-white">
                    {r.next_hop ? r.next_hop : r.subnet_gateway ? (
                      <span title="No next-hop reported by SNMP for this directly-connected route — showing the subnet's configured gateway instead.">
                        <span className="text-gray-200">{r.subnet_gateway}</span>
                        <span className="text-gray-400 text-xs ml-1">(subnet gateway)</span>
                      </span>
                    ) : '—'}
                  </td>
                  <td className="px-5 py-3 text-white">{r.interface ?? '—'}</td>
                  <td className="px-5 py-3">
                    {r.protocol
                      ? <span className={`px-2 py-0.5 rounded text-xs font-medium ${PROTOCOL_BADGE[r.protocol] ?? 'bg-gray-800 text-white border border-gray-700'}`}>{r.protocol}</span>
                      : '—'}
                  </td>
                  <td className="px-5 py-3 text-white">{r.metric ?? '—'}</td>
                  <td className="px-5 py-3 text-white">{r.device_label ?? '—'}</td>
                  <td className="px-5 py-3 text-white text-xs">{r.last_seen}</td>
                </tr>
              ))}
              {routes.length === 0 && (
                <tr><td colSpan={7} className="px-5 py-8 text-center text-white">No routes yet — configure a device (SNMP) collector under Collectors.</td></tr>
              )}
            </tbody>
          </table>
        )}
        {!loading && routes.length > 0 && (
          <div className="px-5 py-2 border-t border-gray-800 text-xs text-white">
            Showing {((pageClamped - 1) * pageSize + 1).toLocaleString()}–{((pageClamped - 1) * pageSize + pagedRoutes.length).toLocaleString()} of {routes.length.toLocaleString()} routes
          </div>
        )}
      </div>
    </div>
  )
}
