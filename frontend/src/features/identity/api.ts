export type Role = 'SuperAdmin' | 'Propietario'

export interface SessionUser {
  id: string
  username: string
  full_name: string
  role: Role
  expires_at: string
}

export class SessionRequestError extends Error {
  constructor(public readonly status: number) {
    super(`La solicitud de sesión devolvió HTTP ${status}`)
  }
}

function isSessionUser(value: unknown): value is SessionUser {
  return typeof value === 'object' && value !== null &&
    'id' in value && typeof value.id === 'string' &&
    'username' in value && typeof value.username === 'string' &&
    'full_name' in value && typeof value.full_name === 'string' &&
    'role' in value && (value.role === 'SuperAdmin' || value.role === 'Propietario') &&
    'expires_at' in value && typeof value.expires_at === 'string' &&
    Number.isFinite(Date.parse(value.expires_at))
}

async function readSession(response: Response): Promise<SessionUser> {
  if (!response.ok) throw new SessionRequestError(response.status)

  const payload: unknown = await response.json()
  if (!isSessionUser(payload)) throw new Error('La respuesta de sesión no tiene el formato esperado.')
  return payload
}

async function fetchSession(path: string, signal: AbortSignal): Promise<SessionUser | null> {
  const response = await fetch(path, {
    signal: AbortSignal.any([signal, AbortSignal.timeout(10_000)]),
  })
  if (response.status === 401) return null
  return readSession(response)
}

export function getCurrentSession(signal: AbortSignal) {
  return fetchSession('/api/auth/me', signal)
}

export function getRoleSession(role: Role, signal: AbortSignal) {
  const section = role === 'SuperAdmin' ? 'admin' : 'owner'
  return fetchSession(`/api/${section}/session`, signal)
}

export async function login(username: string, password: string) {
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Edificios-Request': '1',
    },
    body: JSON.stringify({ username, password }),
    signal: AbortSignal.timeout(10_000),
  })
  return readSession(response)
}

export async function logout() {
  const response = await fetch('/api/auth/logout', {
    method: 'POST',
    headers: { 'X-Edificios-Request': '1' },
    signal: AbortSignal.timeout(10_000),
  })
  if (!response.ok) throw new SessionRequestError(response.status)
}
