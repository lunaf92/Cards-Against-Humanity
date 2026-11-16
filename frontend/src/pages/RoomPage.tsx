import { useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { useRoomStore } from '../stores/roomStore'
import { Notices } from '../components/Notices'
import { ConnectionBanner } from '../components/ConnectionBanner'
import LobbyView from '../views/LobbyView'
import GameView from '../views/GameView'
import GameOverView from '../views/GameOverView'

export default function RoomPage() {
  const { roomId } = useParams<{ roomId: string }>()
  const navigate = useNavigate()
  const connect = useRoomStore((s) => s.connect)
  const disconnect = useRoomStore((s) => s.disconnect)
  const room = useRoomStore((s) => s.room)
  const game = useRoomStore((s) => s.game)
  const gameOver = useRoomStore((s) => s.gameOver)
  const fatalError = useRoomStore((s) => s.fatalError)
  const me = useAuthStore((s) => s.user)

  const meId = me?.id

  useEffect(() => {
    if (!roomId || !meId) return
    connect(roomId, meId)
    return () => disconnect()
  }, [roomId, meId, connect, disconnect])

  if (fatalError) {
    return (
      <main className="screen center stack">
        <p className="error">{fatalError}</p>
        <button className="btn primary" onClick={() => navigate('/')}>
          Back to home
        </button>
      </main>
    )
  }

  if (!room || !me) {
    return (
      <main className="screen center">
        <ConnectionBanner />
        <div className="spinner" aria-label="Connecting" />
      </main>
    )
  }

  let body
  if (gameOver || room.status === 'finished') body = <GameOverView meId={me.id} />
  else if (game) body = <GameView meId={me.id} />
  else body = <LobbyView meId={me.id} />

  return (
    <>
      <ConnectionBanner />
      {body}
      <Notices />
    </>
  )
}
