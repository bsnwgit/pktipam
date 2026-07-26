import { useEffect, useState } from 'react'
import { api, Site } from '../api/client'
import HelpButton from '../components/HelpButton'

function SiteModal({ site, onClose, onSaved }: { site?: Site | null; onClose: () => void; onSaved: () => void }) {
  const editing = !!site
  const [name, setName] = useState(site?.name ?? '')
  const [description, setDescription] = useState(site?.description ?? '')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      const body = { name, description: description || null }
      if (editing) await api.updateSite(site!.id, body)
      else await api.createSite(body)
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
        <h2 className="text-lg font-semibold text-white mb-5">{editing ? `Edit — ${site!.name}` : 'New Site'}</h2>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="text-xs text-white block mb-1">Name</label>
            <input value={name} onChange={e => setName(e.target.value)} required autoFocus className={inp} />
          </div>
          <div>
            <label className="text-xs text-white block mb-1">Description</label>
            <input value={description} onChange={e => setDescription(e.target.value)} className={inp} />
          </div>
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-white">Cancel</button>
            <button type="submit" disabled={saving} className="px-4 py-2 text-sm bg-sky-600 hover:bg-sky-500 text-white rounded-lg disabled:opacity-50">
              {saving ? 'Saving…' : (editing ? 'Save Changes' : 'Create Site')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function Sites() {
  const [sites, setSites] = useState<Site[]>([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<'create' | Site | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<Site | null>(null)

  const load = () => { setLoading(true); api.getSites().then(setSites).finally(() => setLoading(false)) }
  useEffect(load, [])

  const del = async (s: Site) => { await api.deleteSite(s.id); setConfirmDelete(null); load() }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h1 className="text-xl font-bold text-white">Sites</h1>
          <HelpButton title="Sites — How It Works">
            <p>Sites are just labels — a flat list used to tag subnets and VLANs by physical or logical location.</p>
            <p>Deleting a site only removes it from this list and the picker dropdowns — subnets/VLANs already tagged with that name keep their stored value.</p>
          </HelpButton>
        </div>
        <button onClick={() => setModal('create')} className="flex items-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white text-sm rounded-lg">
          <span className="text-base leading-none">+</span> Add Site
        </button>
      </div>
      <p className="text-sm text-white">Sites managed here populate the Site dropdown when creating or editing subnets and VLANs.</p>

      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-32 text-white text-sm">Loading…</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Name</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Description</th>
                <th></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {sites.map(s => (
                <tr key={s.id} className="hover:bg-gray-800/30">
                  <td className="px-5 py-3 text-white">{s.name}</td>
                  <td className="px-5 py-3 text-white">{s.description ?? '—'}</td>
                  <td className="px-5 py-3 text-right">
                    <button onClick={() => setModal(s)} className="p-1.5 text-white hover:text-sky-400">Edit</button>
                    <button onClick={() => setConfirmDelete(s)} className="p-1.5 text-white hover:text-red-400 ml-1">Delete</button>
                  </td>
                </tr>
              ))}
              {sites.length === 0 && <tr><td colSpan={3} className="px-5 py-8 text-center text-white">No sites yet.</td></tr>}
            </tbody>
          </table>
        )}
      </div>

      {modal !== null && (
        <SiteModal site={modal === 'create' ? null : modal} onClose={() => setModal(null)} onSaved={() => { setModal(null); load() }} />
      )}

      {confirmDelete && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 max-w-sm w-full">
            <h3 className="text-white font-semibold mb-2">Delete site?</h3>
            <p className="text-white text-sm mb-5">
              <strong>{confirmDelete.name}</strong> will be removed from the list. Subnets/VLANs already using this
              site name are unaffected — their site field just won't offer it as a dropdown choice anymore.
            </p>
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
