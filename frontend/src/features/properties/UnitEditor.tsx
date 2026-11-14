import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useOutletContext } from 'react-router-dom'

import { PropertyRequestError } from './api'
import { createUnit, unitErrorMessage, unitsPath, updateOwner, updateUnit, type Owner, type OwnerOption, type Unit } from './unitsApi'

function OwnerFields({ owner }: { owner?: Owner }) {
  return (
    <div className="building-form-grid">
      <label>Nombre completo<input name="full_name" defaultValue={owner?.full_name} minLength={3} maxLength={150} required /></label>
      <label>Usuario<input name="username" defaultValue={owner?.username} minLength={3} maxLength={100} autoComplete="off" required /></label>
      <label>Correo<input name="email" type="email" defaultValue={owner?.email ?? ''} maxLength={254} /></label>
      <label>Teléfono<input name="phone" type="tel" defaultValue={owner?.phone ?? ''} maxLength={40} /></label>
      {!owner && <label>Contraseña inicial<input name="password" type="password" minLength={8} maxLength={512} autoComplete="new-password" required /></label>}
    </div>
  )
}

interface UnitEditorProps {
  buildingId: string
  unit?: Unit
  editOwner?: boolean
  owners?: OwnerOption[]
}

export function UnitEditor({ buildingId, unit, editOwner = false, owners = [] }: UnitEditorProps) {
  const navigate = useNavigate()
  const onSessionEnded = useOutletContext<() => void>()
  const [ownerKind, setOwnerKind] = useState<'existing' | 'new'>(owners.length ? 'existing' : 'new')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const roster = unitsPath(buildingId)
  const cancelPath = unit ? `${roster}/${unit.id}` : roster

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const fields = new FormData(event.currentTarget)
    const text = (name: string) => String(fields.get(name) ?? '').trim()
    const profile = {
      full_name: text('full_name'),
      username: text('username'),
      email: text('email') || null,
      phone: text('phone') || null,
    }
    setSaving(true)
    setError('')

    try {
      if (unit && editOwner) {
        await updateOwner(buildingId, unit.id, profile)
        void navigate(cancelPath, { replace: true })
        return
      }

      const input = { number: text('number'), area_sqm: text('area_sqm') }
      const saved = unit
        ? await updateUnit(buildingId, unit.id, input)
        : await createUnit(buildingId, input, ownerKind === 'existing'
          ? { kind: 'existing', id: text('owner_id') }
          : { kind: 'new', ...profile, password: String(fields.get('password') ?? '') })
      void navigate(`${roster}/${saved.id}`, { replace: true })
    } catch (issue) {
      if (issue instanceof PropertyRequestError && issue.status === 401) onSessionEnded()
      else setError(unitErrorMessage(issue, 'No se pudo confirmar el guardado. Revisa el padrón antes de volver a intentarlo.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="building-page building-form-page" aria-labelledby="unit-editor-title">
      <h1 id="unit-editor-title">{editOwner ? 'Editar propietario' : unit ? 'Editar unidad' : 'Nueva unidad'}</h1>
      <form className="building-surface building-form" onSubmit={handleSubmit} aria-busy={saving}>
        {!editOwner && (
          <fieldset disabled={saving}>
            <legend>Datos de la unidad</legend>
            <div className="building-form-grid">
              <label>Número<input name="number" defaultValue={unit?.number} maxLength={60} required /></label>
              <label>Área (m²)<input name="area_sqm" type="number" min="0.01" max="9999999999.99" step="0.01" defaultValue={unit?.area_sqm} required /></label>
            </div>
          </fieldset>
        )}
        {!unit && (
          <fieldset disabled={saving}>
            <legend>Propietario</legend>
            <div className="building-form-grid">
              <label>
                Tipo de propietario
                <select value={ownerKind} onChange={(event) => setOwnerKind(event.target.value === 'existing' ? 'existing' : 'new')}>
                  <option value="existing" disabled={owners.length === 0}>Propietario existente</option>
                  <option value="new">Propietario nuevo</option>
                </select>
              </label>
              {ownerKind === 'existing' && (
                <label>
                  Cuenta del propietario
                  <select name="owner_id" defaultValue="" required>
                    <option value="" disabled>Selecciona una cuenta</option>
                    {owners.map((owner) => <option key={owner.id} value={owner.id}>{owner.full_name} ({owner.username})</option>)}
                  </select>
                </label>
              )}
            </div>
            {ownerKind === 'new' && <div className="owner-fields"><OwnerFields /></div>}
          </fieldset>
        )}
        {editOwner && unit && (
          <fieldset disabled={saving}>
            <legend>Datos del propietario</legend>
            <p>Los cambios se aplican a todas las unidades de esta cuenta.</p>
            <OwnerFields owner={unit.owner} />
          </fieldset>
        )}
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="building-form-actions">
          <button type="submit" disabled={saving}>{saving ? 'Guardando…' : editOwner ? 'Guardar propietario' : 'Guardar unidad'}</button>
          <Link to={cancelPath}>Cancelar</Link>
        </div>
      </form>
    </section>
  )
}
