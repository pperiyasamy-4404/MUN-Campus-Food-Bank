import { useEffect, useState } from 'react'

// Small hooks shared by the pages (13 Nov). Kept out of the component files, so
// the lint rule about fast refresh stays happy.

/** The time now, updated every `every` milliseconds, for live countdowns. */
export function useNow(every = 1000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), every)
    return () => window.clearInterval(timer)
  }, [every])
  return now
}

/** False while the phone or laptop has no internet connection. */
export function useOnline(): boolean {
  const [online, setOnline] = useState(() => (typeof navigator === 'undefined' ? true : navigator.onLine))
  useEffect(() => {
    const on = () => setOnline(true)
    const off = () => setOnline(false)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
    }
  }, [])
  return online
}

/** True if the person's phone or computer asks for less movement on screen. */
export function prefersLessMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true
}
