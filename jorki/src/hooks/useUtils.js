import { useState, useEffect, useRef, useCallback } from 'react'

export function useAnimatedNumber(target, duration = 800) {
  const [value, setValue] = useState(target)
  const fromRef = useRef(target)
  const startRef = useRef(null)
  const rafRef = useRef(null)

  useEffect(() => {
    fromRef.current = value
    startRef.current = null

    const animate = (ts) => {
      if (startRef.current === null) startRef.current = ts
      const elapsed = ts - startRef.current
      const progress = Math.min(elapsed / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      const next = fromRef.current + (target - fromRef.current) * eased
      setValue(next)
      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate)
      }
    }

    rafRef.current = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(rafRef.current)
  }, [target, duration])

  return value
}

export function useLiveData(initial, interval = 2000, variance = 0.05) {
  const [data, setData] = useState(initial)

  useEffect(() => {
    const id = setInterval(() => {
      setData(prev => {
        const next = {}
        for (const key in prev) {
          if (typeof prev[key] === 'number') {
            const delta = prev[key] * variance * (Math.random() - 0.5) * 2
            next[key] = Math.max(0, prev[key] + delta)
          } else {
            next[key] = prev[key]
          }
        }
        return next
      })
    }, interval)
    return () => clearInterval(id)
  }, [interval, variance])

  return data
}

export function useInterval(callback, delay) {
  const savedCallback = useRef(callback)

  useEffect(() => {
    savedCallback.current = callback
  }, [callback])

  useEffect(() => {
    if (delay !== null) {
      const id = setInterval(() => savedCallback.current(), delay)
      return () => clearInterval(id)
    }
  }, [delay])
}

export function formatBytes(bytes) {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

export function formatSpeed(gbps) {
  if (gbps >= 1) return gbps.toFixed(2) + ' GB/s'
  return (gbps * 1024).toFixed(0) + ' MB/s'
}

export function formatNumber(n) {
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K'
  return Math.round(n).toString()
}

export function timeAgo(ts) {
  const seconds = Math.floor((Date.now() - ts) / 1000)
  if (seconds < 60) return seconds + 's ago'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return minutes + 'm ago'
  const hours = Math.floor(minutes / 60)
  return hours + 'h ago'
}
