import { useState, type FormEvent } from 'react'

import { login, SessionRequestError, type SessionUser } from './api'

interface LoginFormProps {
  onSignedIn: (user: SessionUser) => void
}

export function LoginForm({ onSignedIn }: LoginFormProps) {
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setSubmitting(true)
    setError('')

    try {
      onSignedIn(await login(String(form.get('username')), String(form.get('password'))))
    } catch (issue) {
      setError(issue instanceof SessionRequestError && issue.status === 401
        ? 'Usuario o contraseña incorrectos.'
        : 'No se pudo iniciar sesión. Vuelve a intentarlo.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="status-card" aria-labelledby="login-title">
      <h1 id="login-title">Iniciar sesión</h1>
      <form className="login-form" onSubmit={handleSubmit} aria-busy={submitting}>
        <label htmlFor="username">Usuario</label>
        <input id="username" name="username" autoComplete="username" maxLength={100} required />
        <label htmlFor="password">Contraseña</label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          maxLength={512}
          required
        />
        {error && <p className="form-error" role="alert">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? 'Ingresando…' : 'Ingresar'}
        </button>
      </form>
    </section>
  )
}
