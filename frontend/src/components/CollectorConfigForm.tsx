import { Link } from 'react-router-dom'
import { FieldSchema, Site, SnmpCredential, Integration } from '../api/client'
import SiteSelect from './SiteSelect'

/**
 * Renders a structured form for a collector type's config, driven by the
 * FieldSchema list the backend registry describes (app/ipam/collectors/
 * field_schema.py). Replaces hand-editing a raw JSON blob — each field
 * type gets an appropriate input, including repeatable rows for
 * string_list (e.g. DNS zones) and host_list (e.g. SNMP hosts to poll).
 *
 * `show_if` lets a field only render when another top-level field
 * currently equals a given value (e.g. UniFi's auth_method picker hides
 * the username/password fields when API-key mode is selected).
 */

const inputCls = 'w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-sky-500'
const smallBtnCls = 'shrink-0 text-xs text-white border border-gray-700 rounded-lg px-2.5 py-1.5 hover:bg-gray-800 transition-colors'

function FieldWrapper({ field, children }: { field: FieldSchema; children: React.ReactNode }) {
  return (
    <div className="py-3 border-b border-gray-800 last:border-0">
      <label className="block text-xs text-white mb-1">
        {field.label}{field.required && <span className="text-red-400"> *</span>}
      </label>
      {children}
      {field.help && <p className="text-xs text-white mt-1">{field.help}</p>}
    </div>
  )
}

function StringListInput({ field, value, onChange }: {
  field: FieldSchema; value: string[]; onChange: (v: string[]) => void
}) {
  const items = value ?? []
  const setAt = (i: number, v: string) => onChange(items.map((x, idx) => (idx === i ? v : x)))
  const removeAt = (i: number) => onChange(items.filter((_, idx) => idx !== i))
  return (
    <div className="space-y-2">
      {items.map((item, i) => (
        <div key={i} className="flex items-center gap-2">
          <input value={item} onChange={e => setAt(i, e.target.value)}
            placeholder={field.item_placeholder} className={inputCls} />
          <button type="button" onClick={() => removeAt(i)} className={smallBtnCls}>Remove</button>
        </div>
      ))}
      <button type="button" onClick={() => onChange([...items, ''])} className={smallBtnCls}>+ Add {field.label.replace(/s$/, '')}</button>
    </div>
  )
}

function HostListInput({ field, value, onChange, sites }: {
  field: FieldSchema; value: Array<Record<string, string>>; onChange: (v: Array<Record<string, string>>) => void; sites: Site[]
}) {
  const rows = value ?? []
  const subFields = field.sub_fields ?? []
  const setCell = (i: number, key: string, v: string) =>
    onChange(rows.map((row, idx) => (idx === i ? { ...row, [key]: v } : row)))
  const removeAt = (i: number) => onChange(rows.filter((_, idx) => idx !== i))
  const addRow = () => onChange([...rows, Object.fromEntries(subFields.map(sf => [sf.key, '']))])

  return (
    <div className="space-y-2">
      {rows.map((row, i) => (
        <div key={i} className="flex items-center gap-2 flex-wrap bg-gray-800/40 border border-gray-800 rounded-lg p-2">
          {subFields.map(sf => sf.type === 'site_select' ? (
            <SiteSelect
              key={sf.key}
              sites={sites}
              value={row[sf.key] ?? ''}
              onChange={v => setCell(i, sf.key, v)}
              className="flex-1 min-w-[120px] bg-gray-900 border border-gray-700 rounded-lg px-2.5 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
            />
          ) : (
            <input
              key={sf.key}
              value={row[sf.key] ?? ''}
              onChange={e => setCell(i, sf.key, e.target.value)}
              placeholder={sf.placeholder || sf.label}
              className="flex-1 min-w-[120px] bg-gray-900 border border-gray-700 rounded-lg px-2.5 py-1.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-sky-500"
            />
          ))}
          <button type="button" onClick={() => removeAt(i)} className={smallBtnCls}>Remove</button>
        </div>
      ))}
      <button type="button" onClick={addRow} className={smallBtnCls}>+ Add {field.label.replace(/s$/, '')}</button>
      {rows.length === 0 && <p className="text-xs text-white">No entries yet — this collector needs at least one.</p>}
    </div>
  )
}

export default function CollectorConfigForm({ fields, value, onChange, sites, credentials, integrations }: {
  fields: FieldSchema[]
  value: Record<string, unknown>
  onChange: (key: string, v: unknown) => void
  sites: Site[]
  credentials: SnmpCredential[]
  integrations: Integration[]
}) {
  if (fields.length === 0) {
    return <p className="text-sm text-white py-3">This collector type has no configurable fields yet.</p>
  }

  const fieldByKey = Object.fromEntries(fields.map(f => [f.key, f]))
  const resolvedValue = (key: string) => value[key] ?? fieldByKey[key]?.default
  const visibleFields = fields.filter(field => !field.show_if || resolvedValue(field.show_if.key) === field.show_if.equals)

  return (
    <div>
      {visibleFields.map(field => {
        const raw = value[field.key]
        switch (field.type) {
          case 'text':
            return (
              <FieldWrapper key={field.key} field={field}>
                <input value={(raw as string) ?? ''} onChange={e => onChange(field.key, e.target.value)}
                  placeholder={field.placeholder} className={inputCls} />
              </FieldWrapper>
            )
          case 'password':
            return (
              <FieldWrapper key={field.key} field={field}>
                <input type="password" value={(raw as string) ?? ''} onChange={e => onChange(field.key, e.target.value)}
                  placeholder={field.placeholder} className={inputCls} />
              </FieldWrapper>
            )
          case 'number':
            return (
              <FieldWrapper key={field.key} field={field}>
                <input type="number" value={(raw as number) ?? (field.default as number) ?? ''}
                  onChange={e => onChange(field.key, e.target.value === '' ? null : Number(e.target.value))}
                  className={inputCls} />
              </FieldWrapper>
            )
          case 'toggle':
            return (
              <FieldWrapper key={field.key} field={field}>
                <button type="button" onClick={() => onChange(field.key, !((raw as boolean) ?? (field.default as boolean) ?? false))}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${((raw as boolean) ?? (field.default as boolean) ?? false) ? 'bg-sky-600' : 'bg-gray-700'}`}>
                  <span className={`inline-block h-4 w-4 rounded-full bg-white transition-transform ${((raw as boolean) ?? (field.default as boolean) ?? false) ? 'translate-x-6' : 'translate-x-1'}`} />
                </button>
              </FieldWrapper>
            )
          case 'select':
            return (
              <FieldWrapper key={field.key} field={field}>
                <select value={(raw as string) ?? (field.default as string) ?? ''} onChange={e => onChange(field.key, e.target.value)} className={inputCls}>
                  {!field.required && <option value="">—</option>}
                  {(field.options ?? []).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </FieldWrapper>
            )
          case 'multiselect': {
            const selected = (raw as string[]) ?? (field.default as string[]) ?? []
            return (
              <FieldWrapper key={field.key} field={field}>
                <div className="flex flex-wrap gap-3">
                  {(field.options ?? []).map(o => (
                    <label key={o.value} className="flex items-center gap-1.5 text-sm text-white">
                      <input type="checkbox" checked={selected.includes(o.value)}
                        onChange={e => onChange(field.key, e.target.checked
                          ? [...selected, o.value]
                          : selected.filter(v => v !== o.value))} />
                      {o.label}
                    </label>
                  ))}
                </div>
              </FieldWrapper>
            )
          }
          case 'string_list':
            return (
              <FieldWrapper key={field.key} field={field}>
                <StringListInput field={field} value={(raw as string[]) ?? []} onChange={v => onChange(field.key, v)} />
              </FieldWrapper>
            )
          case 'host_list':
            return (
              <FieldWrapper key={field.key} field={field}>
                <HostListInput field={field} value={(raw as Array<Record<string, string>>) ?? []} onChange={v => onChange(field.key, v)} sites={sites} />
              </FieldWrapper>
            )
          case 'site_select':
            return (
              <FieldWrapper key={field.key} field={field}>
                <SiteSelect sites={sites} value={(raw as string) ?? ''} onChange={v => onChange(field.key, v)} className={inputCls} />
              </FieldWrapper>
            )
          case 'credential_select':
            return (
              <FieldWrapper key={field.key} field={field}>
                <select value={(raw as number) ?? ''} onChange={e => onChange(field.key, e.target.value ? Number(e.target.value) : null)} className={inputCls}>
                  <option value="">— Select a credential —</option>
                  {credentials.map(c => <option key={c.id} value={c.id}>{c.name} ({c.snmp_version})</option>)}
                </select>
                {credentials.length === 0 && (
                  <p className="text-xs text-amber-400 mt-1">No SNMP credentials yet — add one under Settings → SNMP Credentials.</p>
                )}
              </FieldWrapper>
            )
          case 'pktsnmp_select':
            return (
              <FieldWrapper key={field.key} field={field}>
                {integrations.length === 0 ? (
                  <p className="text-xs text-amber-400">
                    No pktsnmp connections set up yet —{' '}
                    <Link to="/settings?tab=security&securityTab=suite" className="text-sky-400 hover:text-sky-300 underline">
                      set one up under Settings → Security → Suite Integration
                    </Link>.
                  </p>
                ) : (
                  <select value={(raw as number) ?? ''} onChange={e => onChange(field.key, e.target.value ? Number(e.target.value) : null)} className={inputCls}>
                    <option value="">— Select a pktsnmp connection —</option>
                    {integrations.map(i => <option key={i.id} value={i.id}>{i.name}</option>)}
                  </select>
                )}
              </FieldWrapper>
            )
          default:
            return null
        }
      })}
    </div>
  )
}
