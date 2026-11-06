import { useState } from 'react'

/** Form values kept by name, like { id_number: '', password: '' }. */
export function useValues<T extends Record<string, string>>(start: T) {
  const [values, setValues] = useState(start)
  const set = (name: keyof T) => (value: string) => setValues((old) => ({ ...old, [name]: value }))
  const clear = () => setValues(start)
  return { values, set, clear }
}
