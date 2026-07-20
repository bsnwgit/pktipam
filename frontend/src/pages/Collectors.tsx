import { useEffect, useState } from 'react'
import { api, Collector, CollectorType, CollectorCategory, FieldSchema, Site, SnmpCredential, Integration } from '../api/client'
import CollectorConfigForm from '../components/CollectorConfigForm'

const CATEGORIES: Array<{ id: CollectorCategory; label: string }> = [
  { id: 'dhcp', label: 'DHCP' },
  { id: 'dns', label: 'DNS' },
  { id: 'device', label: 'Device' },
]

function defaultConfigFor(fields: FieldSchema[]): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const f of fields) {
    if (f.default !== undefined) out[f.key] = f.default
    else if (f.type === 'string_list') out[f.key] = []
    else if (f.type === 'host_list') out[f.key] = []
    else if (f.type === 'multiselect') out[f.key] = []
  }
  return out
}

function CollectorModal({ collector, types, sites, credentials, integrations, onClose, onSaved }: {
  collector?: (Collector & { config?: Record<string, unknown> }) | null
  types: Record<string, CollectorType[]>
  sites: Site[]
  credentials: SnmpCredential[]
  integrations: Integration[]
  onClose: () => void
  onSaved: () => void
}) {
  const editing = !!collector
  const [category, setCategory] = useState<CollectorCategory>(collector?.category ?? 'dhcp')
  const [collectorType, setCollectorType] = useState(collector?.collector_type ?? '')
  const [name, setName] = useState(collector?.name ?? '')
  const [pollInterval, setPollInterval] = useState(collector?.poll_interval_sec ?? 300)
  const [enabled, setEnabled] = useState(collector?.enabled ?? true)
  const [config, setConfig] = useState<Record<string, unknown>>(collector?.config ?? {})
  const [showJson, setShowJson] = useState(false)
  const [jsonText, setJsonText] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const typesForCategory = types[category] ?? []
  const selectedType = typesForCategory.find(t => t.type === collectorType)

  useEffect(() => {
    if (!editing && typesForCategory.length && !collectorType) {
      const first = typesForCategory[0]
      setCollectorType(first.type)
      setConfig(defaultConfigFor(first.fields))
    }
  }, [category, typesForCategory])

  const selectType = (type: string) => {
    setCollectorType(type)
    if (!editing) {
      const meta = typesForCategory.find(t => t.type === type)
      setConfig(meta ? defaultConfigFor(meta.fields) : {})
    }
  }

  const setField = (key: string, v: unknown) => setConfig(c => ({ ...c, [key]: v }))

  const openJsonView = () => {
    setJsonText(JSON.stringify(config, null, 2))
    setShowJson(true)
  }

  const closeJsonView = () => {
    try {
      setConfig(JSON.parse(jsonText || '{}'))
      setShowJson(false)
      setError('')
    } catch {
      setError('Config JSON is invalid — fix it or discard changes to go back to the form')
    }
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    let finalConfig = config
    if (showJson) {
      try {
        finalConfig = JSON.parse(jsonText || '{}')
      } catch {
        setError('Config JSON is invalid')
        return
      }
    }
    setSaving(true)
    try {
      const body = { name, category, collector_type: collectorType, config: finalConfig, poll_interval_sec: pollInterval, enabled }
      if (editing) await api.updateCollector(collector!.id, body)
      else await api.createCollector(body)
      onSaved()
    } catch (e: any) {
      setError(e.message ?? 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const inp = 'w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-sky-500'

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 overflow-y-auto py-8" onClick={onClose}>
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-lg p-6" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-white mb-5">{editing ? `Edit — ${collector!.name}` : 'New Collector'}</h2>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="text-xs text-white block mb-1">Name</label>
            <input value={name} onChange={e => setName(e.target.value)} required className={inp} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-white block mb-1">Category</label>
              <select value={category} onChange={e => { setCategory(e.target.value as CollectorCategory); setCollectorType('') }} disabled={editing} className={inp}>
                {CATEGORIES.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-white block mb-1">Type</label>
              <select value={collectorType} onChange={e => selectType(e.target.value)} className={inp}>
                {typesForCategory.map(t => (
                  <option key={t.type} value={t.type}>{t.label}{!t.implemented ? ' (not implemented)' : ''}</option>
                ))}
              </select>
            </div>
          </div>
          {selectedType && !selectedType.implemented && (
            <p className="text-xs text-amber-400">This collector type is a documented stub — creating it will fail on poll until it's implemented.</p>
          )}

          {selectedType && (
            <div className="bg-gray-800/40 border border-gray-800 rounded-lg px-3">
              <div className="flex items-center justify-between pt-2">
                <p className="text-xs font-semibold text-white uppercase tracking-wider">Configuration</p>
                <button type="button" onClick={showJson ? closeJsonView : openJsonView}
                  className="text-xs text-sky-400 hover:text-sky-300">
                  {showJson ? '← Back to form' : 'Edit as JSON'}
                </button>
              </div>
              {showJson ? (
                <div className="py-3">
                  <textarea value={jsonText} onChange={e => setJsonText(e.target.value)} rows={10}
                    className={inp + ' font-mono resize-y'} spellCheck={false} />
                </div>
              ) : (
                <CollectorConfigForm fields={selectedType.fields} value={config} onChange={setField} sites={sites} credentials={credentials} integrations={integrations} />
              )}
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-white block mb-1">Poll interval (sec)</label>
              <input type="number" min={15} value={pollInterval} onChange={e => setPollInterval(Number(e.target.value))} className={inp} />
            </div>
            <div className="flex items-end pb-2">
              <label className="flex items-center gap-2 text-sm text-white">
                <input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} /> Enabled
              </label>
            </div>
          </div>
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-white">Cancel</button>
            <button type="submit" disabled={saving} className="px-4 py-2 text-sm bg-sky-600 hover:bg-sky-500 text-white rounded-lg disabled:opacity-50">
              {saving ? 'Saving…' : (editing ? 'Save Changes' : 'Create Collector')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function PollErrorModal({ message, onClose }: { message: string; onClose: () => void }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      // navigator.clipboard requires a secure context (HTTPS or localhost) —
      // aiserver is typically plain HTTP on the LAN, where it's undefined
      // and this throws immediately. Fall back to the older
      // execCommand('copy') path, which works over plain HTTP.
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(message)
      } else {
        const ta = document.createElement('textarea')
        ta.value = message
        ta.style.position = 'fixed'
        ta.style.opacity = '0'
        document.body.appendChild(ta)
        ta.focus()
        ta.select()
        document.execCommand('copy')
        document.body.removeChild(ta)
      }
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // both clipboard methods unavailable — user can still select the text manually
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 py-8 px-4" onClick={onClose}>
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 max-w-lg w-full" onClick={e => e.stopPropagation()}>
        <h3 className="text-lg font-semibold text-white mb-3">Poll failed</h3>
        <div className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 max-h-64 overflow-y-auto mb-4">
          <p className="text-xs text-red-400 font-mono whitespace-pre-wrap break-all">{message}</p>
        </div>
        <div className="flex items-center justify-between">
          <button onClick={copy} className="text-xs text-sky-400 hover:text-sky-300 transition-colors">
            {copied ? '✓ Copied' : '⧉ Copy to clipboard'}
          </button>
          <button onClick={onClose} className="px-4 py-2 text-sm bg-sky-600 hover:bg-sky-500 text-white rounded-lg">Close</button>
        </div>
      </div>
    </div>
  )
}

export default function Collectors() {
  const [collectors, setCollectors] = useState<Collector[]>([])
  const [types, setTypes] = useState<Record<string, CollectorType[]>>({})
  const [sites, setSites] = useState<Site[]>([])
  const [credentials, setCredentials] = useState<SnmpCredential[]>([])
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<'create' | (Collector & { config?: Record<string, unknown> }) | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<Collector | null>(null)
  const [polling, setPolling] = useState<number | null>(null)
  const [pollResult, setPollResult] = useState<Record<number, string>>({})
  const [pollErrors, setPollErrors] = useState<Record<number, string>>({})
  const [errorModalFor, setErrorModalFor] = useState<number | null>(null)

  const load = () => {
    setLoading(true)
    Promise.all([api.getCollectors(), api.getCollectorTypes(), api.getSites(), api.getSnmpCredentials(), api.getIntegrations()])
      .then(([c, t, s, cr, ig]) => { setCollectors(c); setTypes(t); setSites(s); setCredentials(cr); setIntegrations(ig) })
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const openEdit = async (c: Collector) => {
    const full = await api.getCollector(c.id)
    setModal(full)
  }

  const del = async (c: Collector) => { await api.deleteCollector(c.id); setConfirmDelete(null); load() }

  const pollNow = async (c: Collector) => {
    setPolling(c.id)
    setPollResult(r => ({ ...r, [c.id]: '' }))
    try {
      const res = await api.pollCollectorNow(c.id)
      setPollResult(r => ({ ...r, [c.id]: `OK — ${res.rows} row(s)` }))
    } catch (e: any) {
      const message = e.message ?? 'Poll failed'
      setPollResult(r => ({ ...r, [c.id]: 'Failed — see error' }))
      setPollErrors(r => ({ ...r, [c.id]: message }))
      setErrorModalFor(c.id)
    } finally {
      setPolling(null)
      load()
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Collectors</h1>
        <button onClick={() => setModal('create')} className="flex items-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white text-sm rounded-lg">
          <span className="text-base leading-none">+</span> Add Collector
        </button>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-32 text-white text-sm">Loading…</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Name</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Category</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Type</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Status</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Last Poll</th>
                <th></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {collectors.map(c => (
                <tr key={c.id} className="hover:bg-gray-800/30">
                  <td className="px-5 py-3 text-white">{c.name}{!c.enabled && <span className="text-xs text-white ml-2">(disabled)</span>}</td>
                  <td className="px-5 py-3 text-white uppercase text-xs">{c.category}</td>
                  <td className="px-5 py-3 text-white text-xs">{c.collector_type}</td>
                  <td className="px-5 py-3">
                    <span className={`text-xs font-medium ${c.status === 'ok' ? 'text-emerald-400' : c.status === 'error' ? 'text-red-400' : 'text-white'}`}>
                      {c.status}
                    </span>
                    {c.last_error && <p className="text-xs text-red-400 mt-0.5 max-w-xs truncate" title={c.last_error}>{c.last_error}</p>}
                  </td>
                  <td className="px-5 py-3 text-white text-xs">{c.last_poll_at ?? 'never'}</td>
                  <td className="px-5 py-3 text-right space-x-2 whitespace-nowrap">
                    {pollResult[c.id] && (
                      pollErrors[c.id] ? (
                        <button onClick={() => setErrorModalFor(c.id)} className="text-xs text-red-400 hover:text-red-300 mr-2 underline decoration-dotted">
                          {pollResult[c.id]}
                        </button>
                      ) : (
                        <span className="text-xs text-white mr-2">{pollResult[c.id]}</span>
                      )
                    )}
                    <button onClick={() => pollNow(c)} disabled={polling === c.id} className="text-xs text-white hover:text-sky-400 disabled:opacity-50">
                      {polling === c.id ? 'Polling…' : 'Poll Now'}
                    </button>
                    <button onClick={() => openEdit(c)} className="text-xs text-white hover:text-sky-400">Edit</button>
                    <button onClick={() => setConfirmDelete(c)} className="text-xs text-white hover:text-red-400">Delete</button>
                  </td>
                </tr>
              ))}
              {collectors.length === 0 && <tr><td colSpan={6} className="px-5 py-8 text-center text-white">No collectors configured yet.</td></tr>}
            </tbody>
          </table>
        )}
      </div>

      {modal !== null && (
        <CollectorModal collector={modal === 'create' ? null : modal} types={types} sites={sites} credentials={credentials} integrations={integrations}
          onClose={() => setModal(null)} onSaved={() => { setModal(null); load() }} />
      )}

      {errorModalFor !== null && pollErrors[errorModalFor] && (
        <PollErrorModal message={pollErrors[errorModalFor]} onClose={() => setErrorModalFor(null)} />
      )}

      {confirmDelete && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 max-w-sm w-full">
            <h3 className="text-white font-semibold mb-2">Delete collector?</h3>
            <p className="text-white text-sm mb-5"><strong>{confirmDelete.name}</strong> will be removed along with its raw source data.</p>
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
