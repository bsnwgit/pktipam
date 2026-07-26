import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, Conflict } from '../api/client'
import Pagination from '../components/Pagination'

const PAGE_SIZE = 25

const TYPE_LABEL: Record<string, string> = {
  duplicate_ip: 'Duplicate IP',
  duplicate_mac: 'Duplicate MAC',
  static_dhcp_mismatch: 'Static/DHCP Mismatch',
  dns_mismatch: 'Stale DNS',
  subnet_overlap: 'Subnet Overlap',
  subnet_unrouted: 'Subnet Unrouted',
  route_gateway_mismatch: 'Route/Gateway Mismatch',
}

type Tab = 'active' | 'history'

function matches(c: Conflict, q: string): boolean {
  if (!q) return true
  const needle = q.toLowerCase()
  return (
    (TYPE_LABEL[c.conflict_type] ?? c.conflict_type).toLowerCase().includes(needle) ||
    (c.ip_address ?? '').toLowerCase().includes(needle) ||
    JSON.stringify(c.details).toLowerCase().includes(needle)
  )
}

export default function Conflicts() {
  const [tab, setTab] = useState<Tab>('active')
  const [active, setActive] = useState<Conflict[]>([])
  const [history, setHistory] = useState<Conflict[]>([])
  const [loading, setLoading] = useState(true)
  const [resolving, setResolving] = useState(false)

  const [activeFilter, setActiveFilter] = useState('')
  const [activePage, setActivePage] = useState(1)
  const [selected, setSelected] = useState<Set<number>>(new Set())

  const [historyFilter, setHistoryFilter] = useState('')
  const [historyPage, setHistoryPage] = useState(1)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [a, h] = await Promise.all([
        api.getConflicts({ resolved: false, limit: 500 }),
        api.getConflicts({ resolved: true, limit: 500 }),
      ])
      setActive(a)
      setHistory(h)
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => { load() }, [load])

  useEffect(() => {
    setSelected(s => {
      const activeIds = new Set(active.map(c => c.id))
      const next = new Set(Array.from(s).filter(id => activeIds.has(id)))
      return next.size === s.size ? s : next
    })
  }, [active])

  const resolve = async (c: Conflict) => { await api.resolveConflict(c.id); await load() }
  const ack = async (c: Conflict) => { await api.ackConflict(c.id); await load() }

  const resolveSelected = async () => {
    setResolving(true)
    try {
      await api.resolveSelectedConflicts(Array.from(selected))
      setSelected(new Set())
      await load()
    } finally {
      setResolving(false)
    }
  }

  const resolveAll = async () => {
    setResolving(true)
    try {
      await api.resolveAllConflicts()
      setSelected(new Set())
      await load()
    } finally {
      setResolving(false)
    }
  }

  const toggleOne = (id: number) => {
    setSelected(s => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const filteredActive = useMemo(() => active.filter(c => matches(c, activeFilter)), [active, activeFilter])
  const activeTotalPages = Math.max(1, Math.ceil(filteredActive.length / PAGE_SIZE))
  const activePageClamped = Math.min(activePage, activeTotalPages)
  const pagedActive = filteredActive.slice((activePageClamped - 1) * PAGE_SIZE, activePageClamped * PAGE_SIZE)

  const allFilteredSelected = filteredActive.length > 0 && filteredActive.every(c => selected.has(c.id))
  const toggleAllFiltered = () => {
    setSelected(allFilteredSelected ? new Set() : new Set(filteredActive.map(c => c.id)))
  }

  const filteredHistory = useMemo(() => history.filter(c => matches(c, historyFilter)), [history, historyFilter])
  const historyTotalPages = Math.max(1, Math.ceil(filteredHistory.length / PAGE_SIZE))
  const historyPageClamped = Math.min(historyPage, historyTotalPages)
  const pagedHistory = filteredHistory.slice((historyPageClamped - 1) * PAGE_SIZE, historyPageClamped * PAGE_SIZE)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-bold text-white">Conflicts</h1>
        {tab === 'active' && active.length > 0 && (
          <button onClick={resolveAll} disabled={resolving}
            className="text-sm border border-gray-700 hover:border-gray-500 text-white rounded-lg px-4 py-2 transition-colors disabled:opacity-50">
            {resolving ? 'Resolving…' : 'Resolve all'}
          </button>
        )}
      </div>

      <div className="flex gap-1 bg-gray-900 border border-gray-800 rounded-xl p-1 w-fit">
        {(['active', 'history'] as Tab[]).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`text-sm px-4 py-1.5 rounded-lg transition-colors capitalize ${tab === t ? 'bg-gray-700 text-white' : 'text-white hover:text-white'}`}>
            {t}
            {t === 'active' && active.length > 0 && (
              <span className="ml-1.5 bg-red-500 text-white text-xs rounded-full px-1.5 py-0.5">{active.length}</span>
            )}
          </button>
        ))}
      </div>

      {tab === 'active' && (
        <>
          <div className="flex items-center gap-2 flex-wrap">
            <input value={activeFilter} onChange={e => { setActiveFilter(e.target.value); setActivePage(1) }}
              placeholder="Search type, IP, details…"
              className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white placeholder-gray-600 w-72" />
            {activeFilter && <button onClick={() => { setActiveFilter(''); setActivePage(1) }} className="text-xs text-white hover:text-white">✕</button>}
            {selected.size > 0 && (
              <button onClick={resolveSelected} disabled={resolving}
                className="text-xs bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white rounded-lg px-3 py-1.5 transition-colors">
                {resolving ? 'Resolving…' : `Resolve selected (${selected.size})`}
              </button>
            )}
          </div>

          {!loading && filteredActive.length > 0 && (
            <div className="flex justify-center">
              <Pagination page={activePageClamped} totalPages={activeTotalPages} onChange={setActivePage} />
            </div>
          )}

          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            {loading ? (
              <div className="flex items-center justify-center h-32 text-white text-sm">Loading…</div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-800">
                    <th className="px-5 py-3 w-8">
                      <input type="checkbox" checked={allFilteredSelected} onChange={toggleAllFiltered} />
                    </th>
                    <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Type</th>
                    <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">IP</th>
                    <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Details</th>
                    <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Detected</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800/60">
                  {pagedActive.map(c => (
                    <tr key={c.id} className={`hover:bg-gray-800/30 ${selected.has(c.id) ? 'bg-sky-500/5' : ''}`}>
                      <td className="px-5 py-3">
                        <input type="checkbox" checked={selected.has(c.id)} onChange={() => toggleOne(c.id)} />
                      </td>
                      <td className="px-5 py-3">
                        <span className="px-2 py-0.5 rounded text-xs font-medium bg-red-900/40 text-red-300 border border-red-700/40">
                          {TYPE_LABEL[c.conflict_type] ?? c.conflict_type}
                        </span>
                      </td>
                      <td className="px-5 py-3 font-mono text-white">{c.ip_address ?? '—'}</td>
                      <td className="px-5 py-3 text-white text-xs font-mono">{JSON.stringify(c.details)}</td>
                      <td className="px-5 py-3 text-white text-xs">{c.detected_at}</td>
                      <td className="px-5 py-3 text-right">
                        <button onClick={() => resolve(c)} className="text-xs text-white border border-gray-700 rounded-lg px-3 py-1.5 hover:bg-gray-800">Resolve</button>
                      </td>
                    </tr>
                  ))}
                  {active.length === 0 && (
                    <tr><td colSpan={6} className="px-5 py-8 text-center text-white">No active conflicts.</td></tr>
                  )}
                  {active.length > 0 && filteredActive.length === 0 && (
                    <tr><td colSpan={6} className="px-5 py-8 text-center text-white">No conflicts match this filter.</td></tr>
                  )}
                </tbody>
              </table>
            )}
            {!loading && filteredActive.length > 0 && (
              <div className="px-5 py-2 border-t border-gray-800 text-xs text-white">
                Showing {((activePageClamped - 1) * PAGE_SIZE + 1).toLocaleString()}–{((activePageClamped - 1) * PAGE_SIZE + pagedActive.length).toLocaleString()} of {filteredActive.length.toLocaleString()} conflicts
              </div>
            )}
          </div>
        </>
      )}

      {tab === 'history' && (
        <>
          <div className="flex items-center gap-2">
            <input value={historyFilter} onChange={e => { setHistoryFilter(e.target.value); setHistoryPage(1) }}
              placeholder="Search type, IP, details…"
              className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white placeholder-gray-600 w-72" />
            {historyFilter && <button onClick={() => { setHistoryFilter(''); setHistoryPage(1) }} className="text-xs text-white hover:text-white">✕</button>}
          </div>

          {!loading && filteredHistory.length > 0 && (
            <div className="flex justify-center">
              <Pagination page={historyPageClamped} totalPages={historyTotalPages} onChange={setHistoryPage} />
            </div>
          )}

          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            {loading ? (
              <div className="flex items-center justify-center h-32 text-white text-sm">Loading…</div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-800">
                    <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Type</th>
                    <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">IP</th>
                    <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Details</th>
                    <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Resolved</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800/60">
                  {pagedHistory.map(c => (
                    <tr key={c.id} className="hover:bg-gray-800/30">
                      <td className="px-5 py-3">
                        <span className="px-2 py-0.5 rounded text-xs font-medium bg-red-900/40 text-red-300 border border-red-700/40">
                          {TYPE_LABEL[c.conflict_type] ?? c.conflict_type}
                        </span>
                      </td>
                      <td className="px-5 py-3 font-mono text-white">{c.ip_address ?? '—'}</td>
                      <td className="px-5 py-3 text-white text-xs font-mono">{JSON.stringify(c.details)}</td>
                      <td className="px-5 py-3 text-xs">
                        <span className="text-emerald-400">Resolved by {c.resolved_by}</span>
                        <p className="text-white mt-0.5">{c.resolved_at}</p>
                      </td>
                      <td className="px-5 py-3 text-right">
                        {c.acked ? (
                          <span className="text-xs text-emerald-400">✓ Acked by {c.acked_by}</span>
                        ) : (
                          <button onClick={() => ack(c)} className="text-xs bg-gray-800 hover:bg-gray-700 text-white border border-gray-700 rounded-lg px-3 py-1.5 transition-colors">Ack</button>
                        )}
                      </td>
                    </tr>
                  ))}
                  {history.length === 0 && (
                    <tr><td colSpan={5} className="px-5 py-8 text-center text-white">No resolved conflicts yet.</td></tr>
                  )}
                  {history.length > 0 && filteredHistory.length === 0 && (
                    <tr><td colSpan={5} className="px-5 py-8 text-center text-white">No conflicts match this filter.</td></tr>
                  )}
                </tbody>
              </table>
            )}
            {!loading && filteredHistory.length > 0 && (
              <div className="px-5 py-2 border-t border-gray-800 text-xs text-white">
                Showing {((historyPageClamped - 1) * PAGE_SIZE + 1).toLocaleString()}–{((historyPageClamped - 1) * PAGE_SIZE + pagedHistory.length).toLocaleString()} of {filteredHistory.length.toLocaleString()} conflicts
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
