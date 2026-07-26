import { useEffect, useState } from 'react'
import { api, DnsRecord } from '../api/client'
import Pagination from '../components/Pagination'
import HelpButton from '../components/HelpButton'

const PAGE_SIZE_OPTIONS = [25, 50, 75, 100]

export default function DnsRecords() {
  const [records, setRecords] = useState<DnsRecord[]>([])
  const [recordType, setRecordType] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)

  const load = (searchOverride?: string) => {
    setLoading(true)
    setPage(1)
    api.getDnsRecords({ record_type: recordType || undefined, search: (searchOverride ?? search) || undefined, limit: 500 })
      .then(setRecords).catch(() => {}).finally(() => setLoading(false))
  }
  useEffect(load, [recordType])

  const clearSearch = () => { setSearch(''); load('') }

  const totalPages = Math.max(1, Math.ceil(records.length / pageSize))
  const pageClamped = Math.min(page, totalPages)
  const pagedRecords = records.slice((pageClamped - 1) * pageSize, pageClamped * pageSize)

  const changePageSize = (size: number) => {
    setPageSize(size)
    setPage(1)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h1 className="text-xl font-bold text-white">DNS Records</h1>
        <HelpButton title="DNS Records — How It Works">
          <p>Pulled from your DNS collectors (Pi-hole, Windows DNS, etc). <span className="text-gray-300 font-medium">A/AAAA/CNAME/PTR</span> types are collected as-reported by the server.</p>
          <p>Some A records are synthesized from active or reserved DHCP leases rather than a real zone file entry — those self-clean when the lease is renewed or released. A record with no corroborating lease or ARP entry is flagged as a Stale DNS conflict.</p>
        </HelpButton>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <select value={recordType} onChange={e => setRecordType(e.target.value)} className="bg-gray-800 border border-gray-700 text-white text-sm rounded-lg px-2 py-1.5">
          <option value="">All types</option>
          <option value="A">A</option>
          <option value="AAAA">AAAA</option>
          <option value="CNAME">CNAME</option>
          <option value="PTR">PTR</option>
        </select>
        <div className="flex items-center gap-2">
          <input value={search} onChange={e => setSearch(e.target.value)} onKeyDown={e => e.key === 'Enter' && load()}
            placeholder="Search name or value…"
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white placeholder-gray-600 w-64" />
          {search && <button onClick={clearSearch} className="text-xs text-white hover:text-white">✕</button>}
          <button onClick={() => load()} className="text-xs text-white border border-gray-700 rounded-lg px-3 py-1.5 hover:bg-gray-800">Search</button>
        </div>
      </div>

      {!loading && records.length > 0 && (
        <div className="flex items-center justify-center gap-6">
          <Pagination page={pageClamped} totalPages={totalPages} onChange={setPage} />
          <div className="flex items-center gap-2">
            <label htmlFor="records-per-page" className="text-xs text-gray-400">Records per page:</label>
            <select
              id="records-per-page"
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
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Name</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Type</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Value</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Zone</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">TTL</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {pagedRecords.map(r => (
                <tr key={r.id} className="hover:bg-gray-800/30">
                  <td className="px-5 py-3 font-mono text-white">{r.name}</td>
                  <td className="px-5 py-3"><span className="px-2 py-0.5 rounded text-xs bg-gray-800 text-white border border-gray-700">{r.record_type}</span></td>
                  <td className="px-5 py-3 font-mono text-white">{r.value}</td>
                  <td className="px-5 py-3 text-white">{r.zone}</td>
                  <td className="px-5 py-3 text-white">{r.ttl ?? '—'}</td>
                </tr>
              ))}
              {records.length === 0 && (
                <tr><td colSpan={5} className="px-5 py-8 text-center text-white">No DNS records yet — configure a DNS collector under Collectors.</td></tr>
              )}
            </tbody>
          </table>
        )}
        {!loading && records.length > 0 && (
          <div className="px-5 py-2 border-t border-gray-800 text-xs text-white">
            Showing {((pageClamped - 1) * pageSize + 1).toLocaleString()}–{((pageClamped - 1) * pageSize + pagedRecords.length).toLocaleString()} of {records.length.toLocaleString()} records
          </div>
        )}
      </div>
    </div>
  )
}
