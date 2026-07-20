import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api, Subnet, IpAddress, IpStatus } from '../api/client'

const STATUS_COLOR: Record<IpStatus, string> = {
  free: 'bg-gray-800 border-gray-700 text-white',
  used: 'bg-sky-900/50 border-sky-700 text-sky-200',
  reserved: 'bg-purple-900/50 border-purple-700 text-purple-200',
  dhcp: 'bg-emerald-900/50 border-emerald-700 text-emerald-200',
  static: 'bg-amber-900/50 border-amber-700 text-amber-200',
  conflict: 'bg-red-900/60 border-red-600 text-red-200',
}

function IpDetailModal({ ip, subnetId, onClose, onSaved }: {
  ip: IpAddress; subnetId: number; onClose: () => void; onSaved: () => void
}) {
  const [status, setStatus] = useState<IpStatus>(ip.status === 'free' ? 'static' : ip.status)
  const [hostname, setHostname] = useState(ip.hostname ?? '')
  const [macAddress, setMacAddress] = useState(ip.mac_address ?? '')
  const [description, setDescription] = useState(ip.description ?? '')
  const [owner, setOwner] = useState(ip.owner ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const isNew = ip.id === null

  const save = async () => {
    setSaving(true)
    setError('')
    try {
      const body = { status, hostname: hostname || null, mac_address: macAddress || null, description: description || null, owner: owner || null, tags: [] }
      if (isNew) await api.createManualIp({ ...body, subnet_id: subnetId, ip_address: ip.ip_address })
      else await api.updateIpAddress(ip.id!, body)
      onSaved()
    } catch (e: any) {
      setError(e.message ?? 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const del = async () => {
    if (!ip.id) return
    await api.deleteIpAddress(ip.id)
    onSaved()
  }

  const inp = 'w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-sky-500'

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-md p-6 max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-white mb-1 font-mono">{ip.ip_address}</h2>
        <p className="text-xs text-white mb-5">Source: {ip.source ?? 'none yet'} {ip.last_seen && `· last seen ${ip.last_seen}`}</p>
        <div className="space-y-4">
          <div>
            <label className="text-xs text-white block mb-1">Status</label>
            <select value={status} onChange={e => setStatus(e.target.value as IpStatus)} className={inp}>
              <option value="static">Static reservation</option>
              <option value="reserved">Reserved</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-white block mb-1">Hostname</label>
            <input value={hostname} onChange={e => setHostname(e.target.value)} className={inp} />
          </div>
          <div>
            <label className="text-xs text-white block mb-1">MAC Address</label>
            <input value={macAddress} onChange={e => setMacAddress(e.target.value)} placeholder="aa:bb:cc:dd:ee:ff" className={inp + ' font-mono'} />
          </div>
          <div>
            <label className="text-xs text-white block mb-1">Owner</label>
            <input value={owner} onChange={e => setOwner(e.target.value)} className={inp} />
          </div>
          <div>
            <label className="text-xs text-white block mb-1">Description</label>
            <input value={description} onChange={e => setDescription(e.target.value)} className={inp} />
          </div>
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <div className="flex justify-between items-center pt-2">
            {!isNew && <button onClick={del} className="px-3 py-2 text-sm text-red-400 hover:text-red-300">Delete entry</button>}
            <div className="flex gap-3 ml-auto">
              <button onClick={onClose} className="px-4 py-2 text-sm text-white">Cancel</button>
              <button onClick={save} disabled={saving} className="px-4 py-2 text-sm bg-sky-600 hover:bg-sky-500 text-white rounded-lg disabled:opacity-50">
                {saving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function BulkEditModal({ ipAddresses, subnetId, onClose, onSaved }: {
  ipAddresses: string[]; subnetId: number; onClose: () => void; onSaved: () => void
}) {
  const [applyStatus, setApplyStatus] = useState(false)
  const [status, setStatus] = useState<'static' | 'reserved'>('static')
  const [applyOwner, setApplyOwner] = useState(false)
  const [owner, setOwner] = useState('')
  const [applyDescription, setApplyDescription] = useState(false)
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const anyApplied = applyStatus || applyOwner || applyDescription

  const save = async () => {
    if (!anyApplied) { setError('Check at least one field to apply'); return }
    setSaving(true)
    setError('')
    try {
      const res = await api.bulkUpdateIpAddresses({
        subnet_id: subnetId,
        ip_addresses: ipAddresses,
        apply_status: applyStatus, status,
        apply_owner: applyOwner, owner: owner || null,
        apply_description: applyDescription, description: description || null,
      })
      if (res.updated === 0) { setError('No IPs were updated'); return }
      onSaved()
    } catch (e: any) {
      setError(e.message ?? 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const inp = 'w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-sky-500 disabled:opacity-40'

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-md p-6" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-white mb-1">Bulk Edit — {ipAddresses.length} IPs</h2>
        <p className="text-xs text-white mb-5">
          Check a field to apply it to all selected IPs. Unchecked fields are left as-is.
          Hostname and MAC address can only be edited per-IP.
        </p>
        <div className="space-y-4">
          <div>
            <label className="flex items-center gap-2 text-xs text-white mb-1">
              <input type="checkbox" checked={applyStatus} onChange={e => setApplyStatus(e.target.checked)} /> Status
            </label>
            <select value={status} onChange={e => setStatus(e.target.value as 'static' | 'reserved')} disabled={!applyStatus} className={inp}>
              <option value="static">Static reservation</option>
              <option value="reserved">Reserved</option>
            </select>
          </div>
          <div>
            <label className="flex items-center gap-2 text-xs text-white mb-1">
              <input type="checkbox" checked={applyOwner} onChange={e => setApplyOwner(e.target.checked)} /> Owner
            </label>
            <input value={owner} onChange={e => setOwner(e.target.value)} disabled={!applyOwner} className={inp} />
          </div>
          <div>
            <label className="flex items-center gap-2 text-xs text-white mb-1">
              <input type="checkbox" checked={applyDescription} onChange={e => setApplyDescription(e.target.checked)} /> Description
            </label>
            <input value={description} onChange={e => setDescription(e.target.value)} disabled={!applyDescription} className={inp} />
          </div>
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <div className="flex justify-end gap-3 pt-2">
            <button onClick={onClose} className="px-4 py-2 text-sm text-white">Cancel</button>
            <button onClick={save} disabled={saving || !anyApplied} className="px-4 py-2 text-sm bg-sky-600 hover:bg-sky-500 text-white rounded-lg disabled:opacity-50">
              {saving ? 'Saving…' : `Apply to ${ipAddresses.length} IPs`}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function SubnetDetail() {
  const { id } = useParams()
  const subnetId = Number(id)
  const [subnet, setSubnet] = useState<Subnet | null>(null)
  const [grid, setGrid] = useState<IpAddress[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState<IpAddress | null>(null)
  const [selectedIps, setSelectedIps] = useState<Set<string>>(new Set())
  const [lastClickedIp, setLastClickedIp] = useState<string | null>(null)
  const [showBulkEdit, setShowBulkEdit] = useState(false)

  const load = () => {
    setLoading(true)
    setError('')
    Promise.all([api.getSubnet(subnetId), api.getIpGrid(subnetId)])
      .then(([s, g]) => { setSubnet(s); setGrid(g) })
      .catch(e => setError(e.message ?? 'Failed to load'))
      .finally(() => setLoading(false))
  }
  useEffect(load, [subnetId])
  useEffect(() => { setSelectedIps(new Set()); setLastClickedIp(null) }, [subnetId])

  const handleCellClick = (ip: IpAddress, shiftKey: boolean) => {
    if (shiftKey && lastClickedIp) {
      const ips = grid.map(g => g.ip_address)
      const from = ips.indexOf(lastClickedIp)
      const to = ips.indexOf(ip.ip_address)
      if (from !== -1 && to !== -1) {
        const [lo, hi] = from < to ? [from, to] : [to, from]
        setSelectedIps(prev => {
          const next = new Set(prev)
          for (const addr of ips.slice(lo, hi + 1)) next.add(addr)
          return next
        })
        setLastClickedIp(ip.ip_address)
        return
      }
    }
    setSelectedIps(prev => {
      const next = new Set(prev)
      if (next.has(ip.ip_address)) next.delete(ip.ip_address)
      else next.add(ip.ip_address)
      return next
    })
    setLastClickedIp(ip.ip_address)
  }

  const clearSelection = () => { setSelectedIps(new Set()); setLastClickedIp(null) }

  const openEdit = () => {
    if (selectedIps.size === 1) {
      const ip = grid.find(g => selectedIps.has(g.ip_address))
      if (ip) setEditing(ip)
    } else if (selectedIps.size > 1) {
      setShowBulkEdit(true)
    }
  }

  if (loading) return <div className="flex items-center justify-center h-48 text-white">Loading…</div>
  if (error) return <div className="bg-red-900/30 border border-red-700/50 text-red-400 text-sm rounded-lg px-4 py-3">{error}</div>
  if (!subnet) return null

  return (
    <div className="space-y-4">
      <div>
        <Link to="/subnets" className="text-xs text-sky-400 hover:text-sky-300">← Subnets</Link>
        <h1 className="text-xl font-bold text-white font-mono mt-1">{subnet.cidr}</h1>
        <p className="text-sm text-white">{subnet.description || subnet.site || ''}</p>
      </div>

      {subnet.utilization && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex items-center gap-4">
          <p className="text-sm text-white">
            <span className="text-white font-semibold">{subnet.utilization.used_count}</span> / {subnet.utilization.total_count} used
            &nbsp;·&nbsp; {subnet.utilization.pct_used.toFixed(1)}%
          </p>
        </div>
      )}

      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3 text-xs text-white flex-wrap">
          {(Object.keys(STATUS_COLOR) as IpStatus[]).map(s => (
            <span key={s} className="flex items-center gap-1.5">
              <span className={`w-3 h-3 rounded border ${STATUS_COLOR[s]}`} /> {s}
            </span>
          ))}
        </div>
        <p className="text-xs text-white">Click to select · Shift-click to select a range</p>
      </div>

      {selectedIps.size > 0 && (
        <div className="bg-sky-900/30 border border-sky-700/50 rounded-xl px-4 py-2.5 flex items-center gap-3 sticky top-0 z-10">
          <span className="text-sm text-white font-medium">{selectedIps.size} selected</span>
          <button onClick={openEdit} className="text-xs bg-sky-600 hover:bg-sky-500 text-white rounded-lg px-3 py-1.5">
            {selectedIps.size === 1 ? 'Edit' : 'Bulk Edit'}
          </button>
          <button onClick={clearSelection} className="text-xs text-white hover:text-white border border-gray-700 rounded-lg px-3 py-1.5 hover:bg-gray-800">
            Clear
          </button>
        </div>
      )}

      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <div className="grid grid-cols-[repeat(auto-fill,minmax(90px,1fr))] gap-1.5">
          {grid.map(ip => {
            const isSelected = selectedIps.has(ip.ip_address)
            return (
              <button
                key={ip.ip_address}
                onClick={e => handleCellClick(ip, e.shiftKey)}
                title={`${ip.ip_address}${ip.hostname ? ' — ' + ip.hostname : ''}${ip.mac_address ? ' (' + ip.mac_address + ')' : ''}`}
                className={`text-left px-2 py-1.5 rounded border text-xs font-mono truncate transition-opacity hover:opacity-80 ${STATUS_COLOR[ip.status]} ${isSelected ? 'ring-2 ring-sky-400' : ''}`}
              >
                <div className="truncate">{ip.ip_address.split('.').slice(-1)[0]}</div>
                {ip.hostname && <div className="truncate text-[10px] opacity-80">{ip.hostname}</div>}
              </button>
            )
          })}
        </div>
        {grid.length === 0 && <p className="text-sm text-white text-center py-8">No addresses to display.</p>}
      </div>

      {editing && (
        <IpDetailModal ip={editing} subnetId={subnetId} onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); clearSelection(); load() }} />
      )}

      {showBulkEdit && (
        <BulkEditModal ipAddresses={[...selectedIps]} subnetId={subnetId} onClose={() => setShowBulkEdit(false)}
          onSaved={() => { setShowBulkEdit(false); clearSelection(); load() }} />
      )}
    </div>
  )
}
