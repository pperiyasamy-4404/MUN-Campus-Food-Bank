import { useEffect, useState } from 'react'

type Hello = {
  message: string
}

function App() {
  const [serverMessage, setServerMessage] = useState('Asking the server...')

  // Ask the server for its hello once, when the page first opens.
  useEffect(() => {
    fetch('/api/hello')
      .then((response) => {
        if (!response.ok) {
          throw new Error(`The server answered ${response.status}`)
        }
        return response.json() as Promise<Hello>
      })
      .then((hello) => setServerMessage(hello.message))
      .catch(() => setServerMessage('Could not reach the server. Is it running?'))
  }, [])

  return (
    <main>
      <h1>Hello from the Campus Food Bank</h1>
      <p>The server says: {serverMessage}</p>
    </main>
  )
}

export default App
