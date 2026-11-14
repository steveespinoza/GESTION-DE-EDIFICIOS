import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useOutletContext } from 'react-router-dom'

import { buildingErrorMessage, PropertyRequestError, saveBuilding, type Building, type BuildingInput } from './api'

const paymentFields = [
  { name: 'bank_name', label: 'Banco', maxLength: 150 },
  { name: 'account_holder', label: 'Titular', maxLength: 150 },
  { name: 'account_number', label: 'Número de cuenta', maxLength: 64 },
  { name: 'cci', label: 'CCI', maxLength: 64 },
  { name: 'contact_email', label: 'Correo de contacto', maxLength: 254 },
] as const

function readFields(form: HTMLFormElement): BuildingInput {
  const data = new FormData(form)
  const text = (name: keyof BuildingInput) => String(data.get(name) ?? '').trim()

  return {
    name: text('name'),
    address: text('address') || null,
    total_units: Number(text('total_units')),
    bank_name: text('bank_name') || null,
    account_number: text('account_number') || null,
    cci: text('cci') || null,
    account_holder: text('account_holder') || null,
    contact_email: text('contact_email') || null,
  }
}

export function BuildingForm({ building }: { building?: Building }) {
  const navigate = useNavigate()
  const onSessionEnded = useOutletContext<() => void>()
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const cancelPath = building ? `/admin/edificios/${building.id}` : '/admin'

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const input = readFields(event.currentTarget)
    setSaving(true)
    setError('')

    try {
      const saved = await saveBuilding(input, building?.id)
      void navigate(`/admin/edificios/${saved.id}`, { replace: true })
    } catch (issue) {
      if (issue instanceof PropertyRequestError && issue.status === 401) onSessionEnded()
      else setError(buildingErrorMessage(issue, 'No se pudo guardar el edificio. Vuelve a intentarlo.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="building-page building-form-page" aria-labelledby="building-form-title">
      <h1 id="building-form-title">{building ? 'Editar edificio' : 'Nuevo edificio'}</h1>
      <form className="building-surface building-form" onSubmit={handleSubmit} aria-busy={saving}>
        <fieldset disabled={saving}>
          <legend>Datos generales</legend>
          <div className="building-form-grid">
            <label>
              Nombre
              <input name="name" defaultValue={building?.name} maxLength={150} required />
            </label>
            <label>
              Capacidad de unidades
              <input
                type="number"
                name="total_units"
                min={0}
                max={2147483647}
                step={1}
                defaultValue={building?.total_units ?? 0}
                required
              />
            </label>
            <label className="building-form-wide">
              Dirección
              <input name="address" defaultValue={building?.address ?? ''} maxLength={250} />
            </label>
          </div>
        </fieldset>
        <fieldset disabled={saving}>
          <legend>Instrucciones de pago</legend>
          <div className="building-form-grid">
            {paymentFields.map(({ name, label, maxLength }) => (
              <label key={name}>
                {label}
                <input
                  name={name}
                  type={name === 'contact_email' ? 'email' : 'text'}
                  defaultValue={building?.[name] ?? ''}
                  maxLength={maxLength}
                />
              </label>
            ))}
          </div>
        </fieldset>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="building-form-actions">
          <button type="submit" disabled={saving}>{saving ? 'Guardando…' : 'Guardar edificio'}</button>
          <Link to={cancelPath}>Cancelar</Link>
        </div>
      </form>
    </section>
  )
}
