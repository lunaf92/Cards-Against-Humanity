import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { decksApi } from '../api/endpoints'
import type { RoomDeck } from '../api/types'
import { PlayerList } from '../components/PlayerList'
import { useRoomStore } from '../stores/roomStore'

export default function GameOverView({ meId }: { meId: string }) {
  const navigate = useNavigate()
  const gameOver = useRoomStore((s) => s.gameOver)
  const players = useRoomStore((s) => s.players)
  const room = useRoomStore((s) => s.room)!
  const winner = players.find((p) => p.player_id === gameOver?.winner_player_id)

  let title = 'Game over'
  if (gameOver?.reason === 'not_enough_players') title = 'Not enough players left to keep going'
  else if (gameOver?.winner_player_id === meId) title = 'You won! 🏆'
  else if (winner) title = `${winner.username} wins!`

  return (
    <main className="screen gameover stack">
      <h1 className="center">{title}</h1>
      <section className="panel">
        <h2>Final scores</h2>
        <PlayerList players={players} hostId={room.host_id} meId={meId} showScores />
      </section>
      <CopyDecks decks={(room.decks ?? []).filter((d) => d.is_public && !d.is_builtin && d.owner_id !== meId)} />
      <button className="btn primary big" onClick={() => navigate('/')}>
        Back to home
      </button>
    </main>
  )
}

// Public decks people made that this game used: anyone can take a copy home and add to it.
function CopyDecks({ decks: candidates }: { decks: RoomDeck[] }) {
  const [copies, setCopies] = useState<Record<string, string | 'busy' | 'error'>>({})
  // Decks you already own or co-edit need no copy; wait for that list before offering any.
  const [mine, setMine] = useState<Set<string> | null>(null)
  useEffect(() => {
    let live = true
    decksApi
      .usable()
      .then((list) => live && setMine(new Set(list.filter((d) => !d.is_builtin).map((d) => d.id))))
      .catch(() => live && setMine(new Set()))
    return () => {
      live = false
    }
  }, [])
  const decks = mine ? candidates.filter((d) => !mine.has(d.id) || d.id in copies) : []
  if (decks.length === 0) return null
  async function copy(id: string) {
    setCopies((c) => ({ ...c, [id]: 'busy' }))
    try {
      const deck = await decksApi.copy(id)
      setCopies((c) => ({ ...c, [id]: deck.id }))
    } catch {
      setCopies((c) => ({ ...c, [id]: 'error' }))
    }
  }
  return (
    <section className="panel stack">
      <h2>Decks in this game</h2>
      <p className="hint">Like one? Copy it to your decks and add your own cards.</p>
      <ul className="copy-decks">
        {decks.map((d) => {
          const state = copies[d.id]
          const done = state && state !== 'busy' && state !== 'error'
          return (
            <li key={d.id} className="copy-deck">
              <span className="deck-name">
                {d.name}
                <span className="deck-counts muted">
                  {d.black_count} black · {d.white_count} white
                </span>
              </span>
              {done ? (
                <Link className="btn ghost small" to={`/decks/${state}`}>
                  Copied · Open
                </Link>
              ) : (
                <button className="btn secondary small" disabled={state === 'busy'} onClick={() => void copy(d.id)}>
                  {state === 'error' ? 'Try again' : 'Copy'}
                </button>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
