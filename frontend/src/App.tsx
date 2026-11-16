import { useEffect } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuthStore } from './stores/authStore'
import AuthPage from './pages/AuthPage'
import HomePage from './pages/HomePage'
import RoomPage from './pages/RoomPage'
import DecksPage from './pages/DecksPage'
import DeckPage from './pages/DeckPage'
import JoinDeckPage from './pages/JoinDeckPage'

export default function App() {
  const status = useAuthStore((s) => s.status)
  const init = useAuthStore((s) => s.init)

  useEffect(() => {
    void init()
  }, [init])

  if (status === 'loading') {
    return <div className="screen center muted">Loading…</div>
  }
  if (status === 'signed_out') {
    return <AuthPage />
  }
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/room/:roomId" element={<RoomPage />} />
      <Route path="/decks" element={<DecksPage />} />
      <Route path="/decks/join/:code" element={<JoinDeckPage />} />
      <Route path="/decks/:deckId" element={<DeckPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
