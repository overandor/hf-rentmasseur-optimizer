import { useState, useEffect, useCallback } from 'react'

const API_BASE = ''

export function useJorkiApi() {
  const [health, setHealth] = useState(null)
  const [files, setFiles] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/health`)
      const data = await res.json()
      setHealth(data)
      return data
    } catch (e) {
      setError(e.message)
      return null
    }
  }, [])

  const fetchFiles = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/files`)
      const data = await res.json()
      setFiles(data.files || [])
      return data.files || []
    } catch (e) {
      setError(e.message)
      return []
    }
  }, [])

  const fetchMeta = useCallback(async (fileId) => {
    try {
      const res = await fetch(`${API_BASE}/meta/${fileId}`)
      return await res.json()
    } catch (e) {
      return { error: e.message }
    }
  }, [])

  const fetchSummary = useCallback(async (fileId) => {
    try {
      const res = await fetch(`${API_BASE}/summary/${fileId}`)
      return await res.json()
    } catch (e) {
      return { error: e.message }
    }
  }, [])

  const fetchCapabilities = useCallback(async (fileId) => {
    try {
      const res = await fetch(`${API_BASE}/capabilities/${fileId}`)
      return await res.json()
    } catch (e) {
      return { error: e.message }
    }
  }, [])

  const fetchState = useCallback(async (fileId) => {
    try {
      const res = await fetch(`${API_BASE}/superpose/state/${fileId}`)
      return await res.json()
    } catch (e) {
      return { error: e.message }
    }
  }, [])

  const fetchStats = useCallback(async (fileId) => {
    try {
      const res = await fetch(`${API_BASE}/stats/${fileId}`)
      return await res.json()
    } catch (e) {
      return { error: e.message }
    }
  }, [])

  const search = useCallback(async (fileId, query) => {
    try {
      const res = await fetch(`${API_BASE}/search/${fileId}?q=${encodeURIComponent(query)}`)
      return await res.json()
    } catch (e) {
      return { error: e.message }
    }
  }, [])

  const getChunk = useCallback(async (fileId, idx) => {
    try {
      const res = await fetch(`${API_BASE}/chunk/${fileId}/${idx}`)
      return await res.json()
    } catch (e) {
      return { error: e.message }
    }
  }, [])

  const sqlQuery = useCallback(async (fileId, sql) => {
    try {
      const res = await fetch(`${API_BASE}/query/sql/${fileId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sql }),
      })
      return await res.json()
    } catch (e) {
      return { error: e.message }
    }
  }, [])

  const refresh = useCallback(async () => {
    setLoading(true)
    await Promise.all([fetchHealth(), fetchFiles()])
    setLoading(false)
  }, [fetchHealth, fetchFiles])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 10000)
    return () => clearInterval(id)
  }, [refresh])

  return {
    apiBase: API_BASE,
    health,
    files,
    loading,
    error,
    refresh,
    fetchMeta,
    fetchSummary,
    fetchCapabilities,
    fetchState,
    fetchStats,
    search,
    getChunk,
    sqlQuery,
  }
}
