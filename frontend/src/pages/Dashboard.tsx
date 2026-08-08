import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, Subnet, Conflict, Collector } from '../api/client'
import HelpButton from '../components/HelpButton'

function StatCard({ label, value, accent }: { label: string; value: string | number; accent?: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <p className="text-xs text-white uppercase tracking-wider">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${accent ?? 'text-white'}`}>{value}</p>
    </div>
  )
}

function pctColor(pct: number) {
  if (pct >= 90) return 'bg-red-500'
  if (pct >= 75) return 'bg-amber-500'
  return 'bg-emerald-500'
}

export default function Dashboard() {
  const [subnets, setSubnets] = useState<Subnet[]>([])
  const [conflicts, setConflicts] = useState<Conflict[]>([])
  const [collectors, setCollectors] = useState<Collector[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.getSubnets().catch(() => []),
      api.getConflicts({ resolved: false, limit: 10 }).catch(() => []),
      api.getCollectors().catch(() => []),
    ]).then(([s, c, col]) => { setSubnets(s); setConflicts(c); setCollectors(col) })
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="flex items-center justify-center h-48 text-white">Loading…</div>

  const totalIps = subnets.reduce((sum, s) => sum + (s.utilization?.total_count ?? 0), 0)
  const usedIps = subnets.reduce((sum, s) => sum + (s.utilization?.used_count ?? 0), 0)
  const collectorsErrored = collectors.filter(c => c.status === 'error').length
  const topUtilized = [...subnets]
    .filter(s => s.utilization)
    .sort((a, b) => (b.utilization!.pct_used) - (a.utilization!.pct_used))
    .slice(0, 8)

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <h1 className="text-xl font-bold text-white">Dashboard</h1>
        <HelpButton title="Dashboard — How It Works">
          <p><span className="text-gray-300 font-medium">IPs Tracked</span> is used/total across every configured subnet. <span className="text-gray-300 font-medium">Open Conflicts</span> and <span className="text-gray-300 font-medium">Collectors in Error</span> both link through to their full pages.</p>
          <p>Most Utilized Subnets and Recent Conflicts are live shortcuts — click a subnet bar to open its detail grid, or a conflict to jump to Conflicts.</p>
        </HelpButton>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Subnets" value={subnets.length} />
        <StatCard label="IPs Tracked" value={`${usedIps.toLocaleString()} / ${totalIps.toLocaleString()}`} />
        <StatCard label="Open Conflicts" value={conflicts.length} accent={conflicts.length > 0 ? 'text-red-400' : 'text-white'} />
        <StatCard label="Collectors in Error" value={collectorsErrored} accent={collectorsErrored > 0 ? 'text-amber-400' : 'text-white'} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-800 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-white">Most Utilized Subnets</h2>
            <Link to="/subnets" className="text-xs text-sky-400 hover:text-sky-300">View all →</Link>
          </div>
          <div className="p-4 space-y-3">
            {topUtilized.length === 0 && <p className="text-sm text-white">No subnets configured yet.</p>}
            {topUtilized.map(s => (
              <Link key={s.id} to={`/subnets/${s.id}`} className="block group">
                <div className="flex items-center justify-between text-sm mb-1">
                  <span className="min-w-0 truncate">
                    <span className="text-white font-mono group-hover:text-sky-300">{s.cidr}</span>
                    {s.description && <span className="text-white ml-2">{s.description}</span>}
                  </span>
                  <span className="text-white shrink-0 ml-2">{s.utilization!.pct_used.toFixed(0)}%</span>
                </div>
                <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
                  <div className={`h-full ${pctColor(s.utilization!.pct_used)}`} style={{ width: `${Math.min(100, s.utilization!.pct_used)}%` }} />
                </div>
              </Link>
            ))}
          </div>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-800 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-white">Recent Conflicts</h2>
            <Link to="/conflicts" className="text-xs text-sky-400 hover:text-sky-300">View all →</Link>
          </div>
          <div className="divide-y divide-gray-800/60">
            {conflicts.length === 0 && <p className="text-sm text-white p-4">No unresolved conflicts.</p>}
            {conflicts.map(c => (
              <div key={c.id} className="px-4 py-3">
                <p className="text-sm text-white">
                  <span className="text-red-400 font-medium">{c.conflict_type.replace(/_/g, ' ')}</span>
                  {c.ip_address && <span className="font-mono text-white"> — {c.ip_address}</span>}
                </p>
                <p className="text-xs text-white mt-0.5">{new Date(c.detected_at.replace(' ', 'T') + 'Z').toLocaleString()}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {subnets.length === 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 text-center text-sm text-white">
          No subnets configured yet. Add one under Subnets, then configure a DHCP, DNS, or device collector
          under Collectors to start reconciling real IP usage.
        </div>
      )}
    </div>
  )
}
