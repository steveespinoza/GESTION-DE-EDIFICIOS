import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'

import { PropertyRequestError } from './api'

type PropertyQuery<T> =
  | { status: 'loading' }
  | { status: 'error'; error: unknown }
  | { status: 'ready'; data: T }

export function usePropertyQuery<T>(load: (signal: AbortSignal) => Promise<T>) {
  const onSessionEnded = useOutletContext<() => void>()
  const [query, setQuery] = useState<PropertyQuery<T>>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setQuery({ status: 'ready', data })
      },
      (error: unknown) => {
        if (controller.signal.aborted) return
        if (error instanceof PropertyRequestError && error.status === 401) onSessionEnded()
        else setQuery({ status: 'error', error })
      },
    )
    return () => controller.abort()
  }, [load, onSessionEnded, attempt])

  function retry() {
    setQuery({ status: 'loading' })
    setAttempt((previous) => previous + 1)
  }

  return { query, retry }
}
