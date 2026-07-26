import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, Subnet, Vlan, Site } from '../api/client'
import SiteSelect from '../components/SiteSelect'
import Pagination from '../components/Pagination'

const PAGE_SIZE_OPTIONS = [25, 50, 75, 100]

function pctColor(pct: number) {
  if (pct >= 90) return 'bg-red-500'
  if (pct >= 75) return 'bg-amber-500'
  return 'bg-emerald-500'
}

function SubnetModal({ subnet, vlans, sites, onClose, onSaved }: {
  subnet?: Subnet | null; vlans: Vlan[]; sites: Site[]; onClose: () => void; onSaved: () => void
}) {
  const editing = !!subnet
  const [cidr, setCidr] = useState(subnet?.cidr ?? '')
  const [vlanId, setVlanId] = useState<string>(subnet?.vlan_id ? String(subnet.vlan_id) : '')
  const [site, setSite] = useState(subnet?.site ?? '')
  const [description, setDescription] = useState(subnet?.description ?? '')
  const [descriptionTouched, setDescriptionTouched] = useState(editing && !!subnet?.description)
  const [gateway, setGateway] = useState(subnet?.gateway ?? '')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const selectVlan = (id: string) => {
    setVlanId(id)
    if (!descriptionTouched) {
      const vlan = vlans.find(v => String(v.id) === id)
      setDescription(vlan?.description ?? '')
    }
  }

  const editDescription = (v: string) => {
    setDescription(v)
    setDescriptionTouched(true)
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      const body = { cidr, vlan_id: vlanId ? Number(vlanId) : null, site: site || null, description: description || null, gateway: gateway || null }
      if (editing) await api.updateSubnet(subnet!.id, body)
      else await api.createSubnet(body)
      onSaved()
    } catch (e: any) {
      setError(e.message ?? 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const inp = 'w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-sky-500'

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-md p-6" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-white mb-5">{editing ? `Edit — ${subnet!.cidr}` : 'New Subnet'}</h2>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="text-xs text-white block mb-1">CIDR</label>
            <input value={cidr} onChange={e => setCidr(e.target.value)} placeholder="10.0.1.0/24" required className={inp + ' font-mono'} />
          </div>
          <div>
            <label className="text-xs text-white block mb-1">VLAN</label>
            <select value={vlanId} onChange={e => selectVlan(e.target.value)} className={inp}>
              <option value="">None</option>
              {vlans.map(v => <option key={v.id} value={v.id}>{v.vlan_tag} — {v.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-white block mb-1">Site</label>
            <SiteSelect sites={sites} value={site} onChange={setSite} className={inp} />
          </div>
          <div>
            <label className="text-xs text-white block mb-1">Gateway</label>
            <input value={gateway} onChange={e => setGateway(e.target.value)} placeholder="10.0.1.1" className={inp + ' font-mono'} />
          </div>
          <div>
            <label className="text-xs text-white block mb-1">Description</label>
            <input value={description} onChange={e => editDescription(e.target.value)} placeholder="Auto-filled from VLAN description — edit freely" className={inp} />
          </div>
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-white">Cancel</button>
            <button type="submit" disabled={saving} className="px-4 py-2 text-sm bg-sky-600 hover:bg-sky-500 text-white rounded-lg disabled:opacity-50">
              {saving ? 'Saving…' : (editing ? 'Save Changes' : 'Create Subnet')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function Subnets() {
  const [subnets, setSubnets] = useState<Subnet[]>([])
  const [vlans, setVlans] = useState<Vlan[]>([])
  const [sites, setSites] = useState<Site[]>([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<'create' | Subnet | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<Subnet | null>(null)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)

  const load = () => {
    setLoading(true)
    Promise.all([api.getSubnets(), api.getVlans().catch(() => []), api.getSites().catch(() => [])])
      .then(([s, v, st]) => { setSubnets(s); setVlans(v); setSites(st) })
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const del = async (s: Subnet) => {
    await api.deleteSubnet(s.id)
    setConfirmDelete(null)
    load()
  }

  const filteredSubnets = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return subnets
    return subnets.filter(s =>
      s.cidr.toLowerCase().includes(q) ||
      (s.site ?? '').toLowerCase().includes(q) ||
      (s.description ?? '').toLowerCase().includes(q) ||
      (s.gateway ?? '').toLowerCase().includes(q)
    )
  }, [subnets, search])

  const totalPages = Math.max(1, Math.ceil(filteredSubnets.length / pageSize))
  const pageClamped = Math.min(page, totalPages)
  const pagedSubnets = filteredSubnets.slice((pageClamped - 1) * pageSize, pageClamped * pageSize)

  const changePageSize = (size: number) => {
    setPageSize(size)
    setPage(1)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Subnets</h1>
        <button onClick={() => setModal('create')} className="flex items-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white text-sm rounded-lg">
          <span className="text-base leading-none">+</span> Add Subnet
        </button>
      </div>

      <div className="flex items-center gap-2">
        <input value={search} onChange={e => { setSearch(e.target.value); setPage(1) }}
          placeholder="Search CIDR, site, gateway, description…"
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white placeholder-gray-600 w-72" />
        {search && <button onClick={() => { setSearch(''); setPage(1) }} className="text-xs text-white hover:text-white">✕</button>}
      </div>

      {!loading && filteredSubnets.length > 0 && (
        <div className="flex items-center justify-center gap-6">
          <Pagination page={pageClamped} totalPages={totalPages} onChange={setPage} />
          <div className="flex items-center gap-2">
            <label htmlFor="subnets-per-page" className="text-xs text-gray-400">Subnets per page:</label>
            <select
              id="subnets-per-page"
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
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">CIDR</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Site</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Gateway</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Utilization</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Source</th>
                <th></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {pagedSubnets.map(s => (
                <tr key={s.id} className="hover:bg-gray-800/30">
                  <td className="px-5 py-3.5">
                    <Link to={`/subnets/${s.id}`} className="text-sky-400 hover:text-sky-300 font-mono">{s.cidr}</Link>
                    {s.description && <p className="text-xs text-white mt-0.5">{s.description}</p>}
                  </td>
                  <td className="px-5 py-3.5 text-white">{s.site ?? '—'}</td>
                  <td className="px-5 py-3.5 text-white font-mono">{s.gateway ?? '—'}</td>
                  <td className="px-5 py-3.5 w-48">
                    {s.utilization ? (
                      <div>
                        <div className="flex justify-between text-xs text-white mb-1">
                          <span>{s.utilization.used_count} / {s.utilization.total_count}</span>
                          <span>{s.utilization.pct_used.toFixed(0)}%</span>
                        </div>
                        <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                          <div className={`h-full ${pctColor(s.utilization.pct_used)}`} style={{ width: `${Math.min(100, s.utilization.pct_used)}%` }} />
                        </div>
                      </div>
                    ) : <span className="text-xs text-white">No data yet</span>}
                  </td>
                  <td className="px-5 py-3.5">
                    <span className="px-2 py-0.5 rounded text-xs bg-gray-800 text-white border border-gray-700">{s.source}</span>
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    <button onClick={() => setModal(s)} className="p-1.5 text-white hover:text-sky-400">Edit</button>
                    <button onClick={() => setConfirmDelete(s)} className="p-1.5 text-white hover:text-red-400 ml-1">Delete</button>
                  </td>
                </tr>
              ))}
              {subnets.length === 0 && (
                <tr><td colSpan={6} className="px-5 py-8 text-center text-white">No subnets yet.</td></tr>
              )}
              {subnets.length > 0 && filteredSubnets.length === 0 && (
                <tr><td colSpan={6} className="px-5 py-8 text-center text-white">No subnets match this filter.</td></tr>
              )}
            </tbody>
          </table>
        )}
        {!loading && filteredSubnets.length > 0 && (
          <div className="px-5 py-2 border-t border-gray-800 text-xs text-white">
            Showing {((pageClamped - 1) * pageSize + 1).toLocaleString()}–{((pageClamped - 1) * pageSize + pagedSubnets.length).toLocaleString()} of {filteredSubnets.length.toLocaleString()} subnets
          </div>
        )}
      </div>

      {modal !== null && (
        <SubnetModal subnet={modal === 'create' ? null : modal} vlans={vlans} sites={sites}
          onClose={() => setModal(null)} onSaved={() => { setModal(null); load() }} />
      )}

      {confirmDelete && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 max-w-sm w-full">
            <h3 className="text-white font-semibold mb-2">Delete subnet?</h3>
            <p className="text-white text-sm mb-5"><strong>{confirmDelete.cidr}</strong> and all its reconciled IP data will be removed. This cannot be undone.</p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setConfirmDelete(null)} className="px-4 py-2 text-sm text-white">Cancel</button>
              <button onClick={() => del(confirmDelete)} className="px-4 py-2 text-sm bg-red-600 hover:bg-red-500 text-white rounded-lg">Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
