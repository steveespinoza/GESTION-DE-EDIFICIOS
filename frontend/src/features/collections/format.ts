import type { Period } from './api'

const monthFormatter = new Intl.DateTimeFormat('es-PE', { month: 'long', year: 'numeric', timeZone: 'UTC' })
export const periodLabel = (period: Period) => monthFormatter.format(new Date(Date.UTC(period.billing_year, period.billing_month - 1, 1)))
export const money = (value: string) => `S/ ${value.replace('.', ',')}`
