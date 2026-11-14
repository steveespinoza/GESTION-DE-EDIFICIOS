import { Link, Outlet } from 'react-router-dom'

import { SignOutButton } from '../identity/SignOutButton'
import './properties.css'

export function AdminWorkspace({ onSignedOut }: { onSignedOut: () => void }) {
  return (
    <div className="admin-workspace">
      <div className="workspace-toolbar">
        <nav aria-label="Administración">
          <Link to="/admin">Panel de edificios</Link>
        </nav>
        <SignOutButton onSignedOut={onSignedOut} />
      </div>
      <Outlet context={onSignedOut} />
    </div>
  )
}
