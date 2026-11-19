import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useMatch } from 'react-router-dom'

import { SignOutButton } from '../identity/SignOutButton'
import type { SessionUser } from '../identity/api'
import { PropertyRequestError, readBuilding } from './api'
import { readMyUnit } from './ownerApi'
import { WorkspaceIcon, type WorkspaceIconName } from './WorkspaceIcon'
import './properties.css'
import './workspace.css'

export function PropertyWorkspace({ user, onSignedOut }: { user: SessionUser; onSignedOut: () => void }) {
  const isAdmin = user.role === 'SuperAdmin'
  const buildingMatch = useMatch('/admin/edificios/:buildingId/*')
  const unitMatch = useMatch('/propietario/unidades/:unitId/*')
  const buildingId = isAdmin && buildingMatch?.params.buildingId !== 'nuevo' ? buildingMatch?.params.buildingId : undefined
  const unitId = !isAdmin ? unitMatch?.params.unitId : undefined
  const resource = buildingId ?? unitId
  const home = isAdmin ? '/admin' : '/propietario'
  const homeLabel = isAdmin ? 'Edificios' : 'Mis propiedades'
  const { pathname } = useLocation()
  const dialog = useRef<HTMLDialogElement>(null)
  const content = useRef<HTMLElement>(null)
  const previousPath = useRef(pathname)
  const [menuOpen, setMenuOpen] = useState(false)
  const [context, setContext] = useState<{ resource: string; name: string }>()

  useEffect(() => {
    if (!resource) return
    const controller = new AbortController()
    const identifier = resource
    async function load() {
      try {
        const name = isAdmin ? (await readBuilding(identifier, controller.signal)).name : await readMyUnit(identifier, controller.signal).then((unit) => `${unit.building.name} · Unidad ${unit.number}`)
        if (!controller.signal.aborted) setContext({ resource: identifier, name })
      } catch (error) {
        if (controller.signal.aborted) return
        if (error instanceof PropertyRequestError && error.status === 401) onSignedOut()
        else setContext((previous) => previous?.resource === identifier ? undefined : previous)
      }
    }
    void load()
    return () => controller.abort()
  }, [resource, isAdmin, onSignedOut, pathname])

  useEffect(() => {
    dialog.current?.close()
    if (previousPath.current !== pathname) content.current?.focus()
    previousPath.current = pathname
  }, [pathname])

  useEffect(() => {
    if (!menuOpen) return
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const desktop = window.matchMedia('(min-width: 1024px)')
    const close = () => { if (desktop.matches) dialog.current?.close() }
    desktop.addEventListener('change', close)
    return () => { document.body.style.overflow = previous; desktop.removeEventListener('change', close) }
  }, [menuOpen])

  const label = resource && context?.resource === resource ? context.name : resource ? (isAdmin ? 'Edificio seleccionado' : 'Mi unidad') : homeLabel
  const buildingRoot = `/admin/edificios/${buildingId}`
  const ownerRoot = `/propietario/unidades/${unitId}`
  const links: { to: string; label: string; icon: WorkspaceIconName; end?: boolean }[] = buildingId ? [
    { to: buildingRoot, label: 'Panel de control', icon: 'panel', end: true },
    { to: `${buildingRoot}/unidades`, label: 'Unidades', icon: 'units' },
    { to: `${buildingRoot}/servicios`, label: 'Servicios', icon: 'services' },
    { to: `${buildingRoot}/facturas`, label: 'Facturas y consumos', icon: 'invoice' },
    { to: `${buildingRoot}/reportes-de-pago`, label: 'Reportes de pago', icon: 'payments' },
    { to: `${buildingRoot}/cobranzas`, label: 'Cobranzas', icon: 'collections' },
    { to: `${buildingRoot}/recibos-por-lote`, label: 'Recibos por lote', icon: 'documents' },
  ] : unitId ? [
    { to: ownerRoot, label: 'Mi unidad', icon: 'units', end: true },
    { to: `${ownerRoot}/estado-de-cuenta`, label: 'Estado de cuenta y recibos', icon: 'invoice' },
  ] : []

  function sidebar(mobile = false) {
    return <div className="sidebar-content">
      <div className="sidebar-heading">
        <Link to={home} className="workspace-brand" onClick={() => dialog.current?.close()}><span className="brand-mark">GE</span><span>Gestión de<br /><strong>Edificios</strong></span></Link>
        {mobile && <button type="button" className="sidebar-close" aria-label="Cerrar menú" onClick={() => dialog.current?.close()}><WorkspaceIcon name="close" /></button>}
      </div>
      <div className="workspace-user"><span className="user-avatar" aria-hidden="true">{user.full_name.charAt(0).toUpperCase()}</span><div><strong>{user.full_name}</strong><span>{isAdmin ? 'Administración' : 'Propietario'}</span></div></div>
      {resource && <div className="workspace-context"><span>{isAdmin ? 'Edificio' : 'Propiedad'}</span><strong>{label}</strong></div>}
      <nav className="workspace-nav" aria-label={isAdmin ? 'Administración' : 'Propietario'}>
        <NavLink to={home} end className="workspace-nav-item" onClick={() => dialog.current?.close()}><WorkspaceIcon name="building" />{homeLabel}</NavLink>
        {links.length > 0 && <span className="workspace-nav-label">Espacio de trabajo</span>}
        {links.map((item) => <NavLink key={item.to} to={item.to} end={item.end} className="workspace-nav-item" onClick={() => dialog.current?.close()}><WorkspaceIcon name={item.icon} />{item.label}</NavLink>)}
      </nav>
      <div className="workspace-account"><SignOutButton onSignedOut={onSignedOut} /></div>
    </div>
  }

  return <div className="property-workspace workspace-shell">
    <a href="#workspace-content" className="skip-link">Saltar al contenido</a>
    <aside className="workspace-sidebar">{sidebar()}</aside>
    <div className="workspace-mobile-bar"><button type="button" aria-label="Abrir menú" aria-expanded={menuOpen} aria-controls="workspace-mobile-menu" onClick={() => { dialog.current?.showModal(); setMenuOpen(true) }}><WorkspaceIcon name="menu" /></button><span>{label}</span><span className="mobile-avatar" aria-hidden="true">{user.full_name.charAt(0).toUpperCase()}</span></div>
    <dialog ref={dialog} id="workspace-mobile-menu" className="workspace-mobile-menu" aria-label="Menú de navegación" onClose={() => setMenuOpen(false)} onClick={(event) => { if (event.target === event.currentTarget) dialog.current?.close() }}>{sidebar(true)}</dialog>
    <main ref={content} id="workspace-content" className="workspace-main" tabIndex={-1}>
      <div className="workspace-breadcrumb"><Link to={home}>{homeLabel}</Link>{resource && <><span aria-hidden="true">/</span><span>{label}</span></>}</div>
      <Outlet context={onSignedOut} />
    </main>
  </div>
}
