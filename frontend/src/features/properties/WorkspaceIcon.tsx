export type WorkspaceIconName = 'building' | 'panel' | 'units' | 'services' | 'invoice' | 'collections' | 'payments' | 'documents' | 'menu' | 'close' | 'arrow'

const paths: Record<WorkspaceIconName, string> = {
  building: 'M4 21V4h12v17M16 9h4v12M2 21h20M8 8h4M8 12h4M8 16h4',
  panel: 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
  units: 'm3 11 9-8 9 8M5 9v12h14V9M9 21v-7h6v7',
  services: 'M4 7h16M4 17h16M8 4v6M16 14v6',
  invoice: 'M6 3h9l4 4v14H6zM14 3v5h5M9 12h7M9 16h7',
  collections: 'M3 6h18v13H3zM3 10h18M7 15h3M15 15h2',
  payments: 'M5 3h14v18l-3-2-4 2-4-2-3 2zM8 8h8M8 12h8',
  documents: 'M8 3h12v14H8zM4 7v14h12M11 7h6M11 11h6',
  menu: 'M4 6h16M4 12h16M4 18h16',
  close: 'm6 6 12 12M6 18 18 6',
  arrow: 'm9 5 7 7-7 7',
}

export function WorkspaceIcon({ name }: { name: WorkspaceIconName }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><path d={paths[name]} /></svg>
}
