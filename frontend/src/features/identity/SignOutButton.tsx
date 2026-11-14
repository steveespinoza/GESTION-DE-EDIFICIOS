import { useState } from 'react'

import { logout } from './api'

export function SignOutButton({ onSignedOut }: { onSignedOut: () => void }) {
  const [signingOut, setSigningOut] = useState(false)
  const [failed, setFailed] = useState(false)

  async function handleSignOut() {
    setSigningOut(true)
    setFailed(false)
    try {
      await logout()
      onSignedOut()
    } catch {
      setFailed(true)
    } finally {
      setSigningOut(false)
    }
  }

  return (
    <div>
      <button type="button" onClick={handleSignOut} disabled={signingOut}>
        {signingOut ? 'Cerrando sesión…' : 'Cerrar sesión'}
      </button>
      {failed && <p className="form-error" role="alert">No se pudo cerrar la sesión. Vuelve a intentarlo.</p>}
    </div>
  )
}
