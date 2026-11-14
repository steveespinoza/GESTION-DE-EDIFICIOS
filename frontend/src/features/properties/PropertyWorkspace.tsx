import { Link, Outlet } from 'react-router-dom'

import { SignOutButton } from '../identity/SignOutButton'
import type { Role } from '../identity/api'
import './properties.css'

export function PropertyWorkspace({ role, onSignedOut }: { role: Role; onSignedOut: () => void }) {
  const isAdmin = role === 'SuperAdmin'

  return (
    <div className="property-workspace">
      <div className="workspace-toolbar">
        <nav aria-label={isAdmin ? 'Administración' : 'Propietario'}>
          <Link to={isAdmin ? '/admin' : '/propietario'}>
            {isAdmin ? 'Panel de edificios' : 'Mis propiedades'}
          </Link>
        </nav>
        <SignOutButton onSignedOut={onSignedOut} />
      </div>
      <Outlet context={onSignedOut} />
    </div>
  )
}
