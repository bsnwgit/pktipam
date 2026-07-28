import { useEffect, useState } from 'react'
import { api, CapacityCandidate, Subnet } from '../api/client'

const inp = 'w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-sky-500'

function ReserveModal({ candidate, onClose, onSaved }: { candidate: CapacityCandidate; onClose: () => void; onSaved: () => void }) {
  const [description, setDescription] = useState('')
  const [owner, setOwner] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      await api.reserveCapacity({
        subnet_id: candidate.subnet_id,
        start_ip: candidate.start_ip,
        end_ip: candidate.end_ip,
        description: description || null,
        owner: owner || null,
      })
      onSaved()
    } catch (e: any) {
      setError(e.message ?? 'Reservation failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-sm p-6" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-white mb-1">Reserve Range</h2>
        <p className="text-xs text-white/70 font-mono mb-5">
          {candidate.cidr ?? `${candidate.start_ip} – ${candidate.end_ip}`} in {candidate.subnet_cidr} ({candidate.size} addresses)
        </p>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="text-xs text-white block mb-1">Description</label>
            <input value={description} onChange={e => setDescription(e.target.value)} placeholder="e.g. reserved for VoIP rollout" className={inp} />
          </div>
          <div>
            <label className="text-xs text-white block mb-1">Owner</label>
            <input value={owner} onChange={e => setOwner(e.target.value)} placeholder="e.g. team or requester" className={inp} />
          </div>
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-white">Cancel</button>
            <button type="submit" disabled={saving} className="px-4 py-2 text-sm bg-sky-600 hover:bg-sky-500 text-white rounded-lg disabled:opacity-50">
              {saving ? 'Reserving…' : 'Create Reservation'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function CapacityPlanner() {
  const [subnets, setSubnets] = useState<Subnet[]>([])
  const [hostCount, setHostCount] = useState(50)
  const [bufferPct, setBufferPct] = useState(20)
  const [subnetId, setSubnetId] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<{ prefix: number; block_size: number; usable_hosts: number; required_hosts: number; candidates: CapacityCandidate[] } | null>(null)
  const [reserveTarget, setReserveTarget] = useState<CapacityCandidate | null>(null)
  const [reservedMsg, setReservedMsg] = useState('')

  useEffect(() => { api.getSubnets().then(setSubnets).catch(() => {}) }, [])

  const subnetLabel = (id: number) => subnets.find(s => s.id === id)?.cidr ?? id

  const run = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    setResult(null)
    setReservedMsg('')
    try {
      const res = await api.searchCapacity({
        host_count: hostCount,
        buffer_pct: bufferPct,
        subnet_id: subnetId ? Number(subnetId) : undefined,
      })
      setResult(res)
    } catch (e: any) {
      setError(e.message ?? 'Calculation failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold text-white">Capacity Planner</h1>
      <p className="text-sm text-white/70">Work out how much address space a project needs, find where it fits, and reserve it.</p>

      <form onSubmit={run} className="bg-gray-900 border border-gray-800 rounded-xl p-5 flex items-end gap-4 flex-wrap">
        <div>
          <label className="text-xs text-white block mb-1">Hosts needed</label>
          <input type="number" min={1} value={hostCount} onChange={e => setHostCount(Number(e.target.value))} required
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white w-32 focus:outline-none focus:border-sky-500" />
        </div>
        <div>
          <label className="text-xs text-white block mb-1">Growth buffer %</label>
          <input type="number" min={0} value={bufferPct} onChange={e => setBufferPct(Number(e.target.value))}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white w-32 focus:outline-none focus:border-sky-500" />
        </div>
        <div>
          <label className="text-xs text-white block mb-1">Search within</label>
          <select value={subnetId} onChange={e => setSubnetId(e.target.value)}
            className="bg-gray-800 border border-gray-700 text-white text-sm rounded-lg px-3 py-2">
            <option value="">All subnets</option>
            {subnets.map(s => <option key={s.id} value={s.id}>{s.cidr}{s.description ? ` — ${s.description}` : ''}</option>)}
          </select>
        </div>
        <button type="submit" disabled={loading} className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white text-sm rounded-lg disabled:opacity-50">
          {loading ? 'Calculating…' : 'Calculate'}
        </button>
      </form>

      {error && <p className="text-red-400 text-sm">{error}</p>}
      {reservedMsg && <p className="text-emerald-400 text-sm">{reservedMsg}</p>}

      {result && (
        <div className="space-y-4">
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 flex items-center gap-8 flex-wrap text-sm">
            <div><span className="text-white/60">Required (with buffer):</span> <span className="text-white font-semibold">{result.required_hosts} hosts</span></div>
            <div><span className="text-white/60">Smallest block:</span> <span className="text-white font-semibold">/{result.prefix}</span> ({result.block_size} addresses, {result.usable_hosts} usable)</div>
          </div>

          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Subnet</th>
                  <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Candidate Range</th>
                  <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Size</th>
                  <th className="text-left px-5 py-3 text-xs font-medium text-white uppercase tracking-wider">Aligned CIDR</th>
                  <th></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/60">
                {result.candidates.map((c, i) => (
                  <tr key={i} className="hover:bg-gray-800/30">
                    <td className="px-5 py-3 text-white font-mono">{c.subnet_cidr}</td>
                    <td className="px-5 py-3 text-white font-mono">{c.cidr ?? `${c.start_ip} – ${c.end_ip}`}</td>
                    <td className="px-5 py-3 text-white">{c.size}</td>
                    <td className="px-5 py-3 text-white">{c.aligned ? 'Yes' : 'No (fragmented free space)'}</td>
                    <td className="px-5 py-3 text-right">
                      <button onClick={() => setReserveTarget(c)} className="px-3 py-1.5 bg-sky-600 hover:bg-sky-500 text-white text-xs rounded-lg">
                        Reserve
                      </button>
                    </td>
                  </tr>
                ))}
                {result.candidates.length === 0 && (
                  <tr><td colSpan={5} className="px-5 py-8 text-center text-white">No free block of this size found{subnetId ? ' in this subnet' : ''}.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {reserveTarget && (
        <ReserveModal
          candidate={reserveTarget}
          onClose={() => setReserveTarget(null)}
          onSaved={() => {
            setReservedMsg(`Reserved ${reserveTarget.start_ip} – ${reserveTarget.end_ip} in ${subnetLabel(reserveTarget.subnet_id)}.`)
            setReserveTarget(null)
            setResult(r => r ? { ...r, candidates: r.candidates.filter(c => c !== reserveTarget) } : r)
          }}
        />
      )}
    </div>
  )
}
