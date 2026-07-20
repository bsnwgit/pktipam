import { Site } from '../api/client'

/**
 * Site picker dropdown, populated from the managed Sites list (Settings
 * -> Sites page). Always includes the current value as an option even if
 * it's not (or no longer) in the sites list, so editing a subnet/VLAN
 * with a legacy free-typed site name never silently blanks it out.
 */
export default function SiteSelect({ sites, value, onChange, className }: {
  sites: Site[]; value: string; onChange: (v: string) => void; className: string
}) {
  const names = sites.map(s => s.name)
  const options = value && !names.includes(value) ? [value, ...names] : names

  return (
    <select value={value} onChange={e => onChange(e.target.value)} className={className}>
      <option value="">—</option>
      {options.map(name => <option key={name} value={name}>{name}</option>)}
    </select>
  )
}
