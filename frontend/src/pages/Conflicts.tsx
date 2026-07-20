import { useEffect, useState } from 'react'
import { api, Conflict } from '../api/client'
import Pagination from '../components/Pagination'

const PAGE_SIZE = 25

const TYPE_LABEL: Record<string, string> = {
  duplicate_ip: 'Duplicate IP',
  duplicate_mac: 'Duplicate MAC',
  static_dhcp_mismatch: 'Static/DHCP Mismatch',
  dns_mismatch: 'Stale DNS',
  subnet_overlap: 'Subnet Overlap',
}

export default function Conflicts() {
  const [conflicts, setConflicts] = useState<Conflict[]>([])
  const [showResolved, setShowResolved] = useState(false)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)

  const load = () => {
    setLoading(true)
    setPage(1)
    api.getConflicts({ resolved: showResolved ? undefined : false, limit: 500 })
      .then(setConflicts).catch(() => {}).finally(() => setLoading(false))
  }
  useEffect(load, [showResolved])

  const resolve = async (c: Conflict) => {
    await api.resolveConflict(c.id)
    load()
  }

  const totalPages = Math.max(1, Math.ceil(conflicts.length / PAGE_SIZE))
  const pageClamped = Math.min(page, totalPages)
  const pagedConflicts = conflicts.slice((pageClamped - 1) * PAGE_SIZE, pageClamped * PAGE_SIZE)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Conflicts</h1>
        <label className="flex items-center gap-2 text-sm text-white">
          <input type="checkbox" checked={showResolved} onChange={e => setShowResolved(e.target.checked)} />
          Show resolved
        </label>
      </div>

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
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Detected</th>
                <th></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {pagedConflicts.map(c => (
                <tr key={c.id} className="hover:bg-gray-800/30">
                  <td className="px-5 py-3">
                    <span className="px-2 py-0.5 rounded text-xs font-medium bg-red-900/40 text-red-300 border border-red-700/40">
                      {TYPE_LABEL[c.conflict_type] ?? c.conflict_type}
                    </span>
                  </td>
                  <td className="px-5 py-3 font-mono text-white">{c.ip_address ?? '—'}</td>
                  <td className="px-5 py-3 text-white text-xs font-mono">{JSON.stringify(c.details)}</td>
                  <td className="px-5 py-3 text-white text-xs">{c.detected_at}</td>
                  <td className="px-5 py-3 text-right">
                    {!c.resolved_at ? (
                      <button onClick={() => resolve(c)} className="text-xs text-white border border-gray-700 rounded-lg px-3 py-1.5 hover:bg-gray-800">Resolve</button>
                    ) : (
                      <span className="text-xs text-emerald-400">Resolved by {c.resolved_by}</span>
                    )}
                  </td>
                </tr>
              ))}
              {conflicts.length === 0 && (
                <tr><td colSpan={5} className="px-5 py-8 text-center text-white">No conflicts detected.</td></tr>
              )}
            </tbody>
          </table>
        )}
        {!loading && conflicts.length > 0 && (
          <div className="px-5 py-2 border-t border-gray-800 flex items-center justify-between text-xs text-white">
            <span>
              Showing {((pageClamped - 1) * PAGE_SIZE + 1).toLocaleString()}–{((pageClamped - 1) * PAGE_SIZE + pagedConflicts.length).toLocaleString()} of {conflicts.length.toLocaleString()} conflicts
            </span>
            <Pagination page={pageClamped} totalPages={totalPages} onChange={setPage} />
          </div>
        )}
      </div>
    </div>
  )
}
