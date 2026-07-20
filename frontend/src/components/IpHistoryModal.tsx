import { useEffect, useState } from 'react'
import { api, IpAddressHistoryEntry } from '../api/client'

const HISTORY_EVENT_LABEL: Record<IpAddressHistoryEntry['event'], string> = {
  first_seen: 'First seen',
  changed: 'Changed',
  released: 'Released',
}
const HISTORY_EVENT_COLOR: Record<IpAddressHistoryEntry['event'], string> = {
  first_seen: 'text-emerald-400',
  changed: 'text-amber-400',
  released: 'text-white',
}

export default function IpHistoryModal({ ipAddress, onClose }: { ipAddress: string; onClose: () => void }) {
  const [entries, setEntries] = useState<IpAddressHistoryEntry[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getIpAddressHistory({ ip_address: ipAddress, limit: 50 }).then(setEntries).catch(() => {}).finally(() => setLoading(false))
  }, [ipAddress])

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-md p-6 max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-white mb-1 font-mono">{ipAddress}</h2>
        <p className="text-xs text-white mb-4">Assignment history</p>

        {loading ? (
          <p className="text-xs text-white">Loading history…</p>
        ) : entries.length === 0 ? (
          <p className="text-xs text-white">No history recorded yet for this IP.</p>
        ) : (
          <div className="space-y-2">
            {entries.map(e => (
              <div key={e.id} className="text-xs border-l-2 border-gray-700 pl-3 py-0.5">
                <div className="flex items-center gap-2">
                  <span className={`font-medium ${HISTORY_EVENT_COLOR[e.event]}`}>{HISTORY_EVENT_LABEL[e.event]}</span>
                  <span className="text-white">{e.recorded_at}</span>
                </div>
                <p className="text-white font-mono mt-0.5">
                  {e.mac_address ?? '—'}{e.hostname && ` · ${e.hostname}`}{e.source && ` · via ${e.source}`}
                </p>
              </div>
            ))}
          </div>
        )}

        <div className="flex justify-end pt-4">
          <button onClick={onClose} className="px-4 py-2 text-sm bg-sky-600 hover:bg-sky-500 text-white rounded-lg">Close</button>
        </div>
      </div>
    </div>
  )
}
