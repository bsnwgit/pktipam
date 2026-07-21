import { useEffect, useMemo, useState } from 'react'
import { api, Vlan, Site } from '../api/client'
import SiteSelect from '../components/SiteSelect'
import Pagination from '../components/Pagination'

const PAGE_SIZE = 25

function VlanModal({ vlan, sites, onClose, onSaved }: { vlan?: Vlan | null; sites: Site[]; onClose: () => void; onSaved: () => void }) {
  const editing = !!vlan
  const [vlanTag, setVlanTag] = useState(vlan?.vlan_tag ?? 1)
  const [name, setName] = useState(vlan?.name ?? '')
  const [site, setSite] = useState(vlan?.site ?? '')
  const [description, setDescription] = useState(vlan?.description ?? '')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      const body = { vlan_tag: vlanTag, name, site: site || null, description: description || null }
      if (editing) await api.updateVlan(vlan!.id, body)
      else await api.createVlan(body)
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
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-sm p-6" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-white mb-5">{editing ? `Edit VLAN ${vlan!.vlan_tag}` : 'New VLAN'}</h2>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="text-xs text-white block mb-1">VLAN Tag</label>
            <input type="number" min={1} max={4094} value={vlanTag} onChange={e => setVlanTag(Number(e.target.value))} required className={inp} />
          </div>
          <div>
            <label className="text-xs text-white block mb-1">Name</label>
            <input value={name} onChange={e => setName(e.target.value)} required className={inp} />
          </div>
          <div>
            <label className="text-xs text-white block mb-1">Site</label>
            <SiteSelect sites={sites} value={site} onChange={setSite} className={inp} />
          </div>
          <div>
            <label className="text-xs text-white block mb-1">Description</label>
            <input value={description} onChange={e => setDescription(e.target.value)} className={inp} />
          </div>
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-white">Cancel</button>
            <button type="submit" disabled={saving} className="px-4 py-2 text-sm bg-sky-600 hover:bg-sky-500 text-white rounded-lg disabled:opacity-50">
              {saving ? 'Saving…' : (editing ? 'Save Changes' : 'Create VLAN')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function Vlans() {
  const [vlans, setVlans] = useState<Vlan[]>([])
  const [sites, setSites] = useState<Site[]>([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<'create' | Vlan | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<Vlan | null>(null)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)

  const load = () => {
    setLoading(true)
    Promise.all([api.getVlans(), api.getSites().catch(() => [])])
      .then(([v, st]) => { setVlans(v); setSites(st) })
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const del = async (v: Vlan) => { await api.deleteVlan(v.id); setConfirmDelete(null); load() }

  const filteredVlans = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return vlans
    return vlans.filter(v =>
      String(v.vlan_tag).includes(q) ||
      v.name.toLowerCase().includes(q) ||
      (v.site ?? '').toLowerCase().includes(q) ||
      (v.description ?? '').toLowerCase().includes(q)
    )
  }, [vlans, search])

  const totalPages = Math.max(1, Math.ceil(filteredVlans.length / PAGE_SIZE))
  const pageClamped = Math.min(page, totalPages)
  const pagedVlans = filteredVlans.slice((pageClamped - 1) * PAGE_SIZE, pageClamped * PAGE_SIZE)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">VLANs</h1>
        <button onClick={() => setModal('create')} className="flex items-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white text-sm rounded-lg">
          <span className="text-base leading-none">+</span> Add VLAN
        </button>
      </div>

      <div className="flex items-center gap-2">
        <input value={search} onChange={e => { setSearch(e.target.value); setPage(1) }}
          placeholder="Search tag, name, site, description…"
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white placeholder-gray-600 w-72" />
        {search && <button onClick={() => { setSearch(''); setPage(1) }} className="text-xs text-white hover:text-white">✕</button>}
      </div>

      {!loading && filteredVlans.length > 0 && (
        <div className="flex justify-center">
          <Pagination page={pageClamped} totalPages={totalPages} onChange={setPage} />
        </div>
      )}

      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-32 text-white text-sm">Loading…</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Tag</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Name</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Site</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Description</th>
                <th></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {pagedVlans.map(v => (
                <tr key={v.id} className="hover:bg-gray-800/30">
                  <td className="px-5 py-3 font-mono text-white">{v.vlan_tag}</td>
                  <td className="px-5 py-3 text-white">{v.name}</td>
                  <td className="px-5 py-3 text-white">{v.site ?? '—'}</td>
                  <td className="px-5 py-3 text-white">{v.description ?? '—'}</td>
                  <td className="px-5 py-3 text-right">
                    <button onClick={() => setModal(v)} className="p-1.5 text-white hover:text-sky-400">Edit</button>
                    <button onClick={() => setConfirmDelete(v)} className="p-1.5 text-white hover:text-red-400 ml-1">Delete</button>
                  </td>
                </tr>
              ))}
              {vlans.length === 0 && <tr><td colSpan={5} className="px-5 py-8 text-center text-white">No VLANs yet.</td></tr>}
              {vlans.length > 0 && filteredVlans.length === 0 && (
                <tr><td colSpan={5} className="px-5 py-8 text-center text-white">No VLANs match this filter.</td></tr>
              )}
            </tbody>
          </table>
        )}
        {!loading && filteredVlans.length > 0 && (
          <div className="px-5 py-2 border-t border-gray-800 text-xs text-white">
            Showing {((pageClamped - 1) * PAGE_SIZE + 1).toLocaleString()}–{((pageClamped - 1) * PAGE_SIZE + pagedVlans.length).toLocaleString()} of {filteredVlans.length.toLocaleString()} VLANs
          </div>
        )}
      </div>

      {modal !== null && (
        <VlanModal vlan={modal === 'create' ? null : modal} sites={sites} onClose={() => setModal(null)} onSaved={() => { setModal(null); load() }} />
      )}

      {confirmDelete && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 max-w-sm w-full">
            <h3 className="text-white font-semibold mb-2">Delete VLAN?</h3>
            <p className="text-white text-sm mb-5"><strong>{confirmDelete.vlan_tag} — {confirmDelete.name}</strong> will be removed.</p>
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
