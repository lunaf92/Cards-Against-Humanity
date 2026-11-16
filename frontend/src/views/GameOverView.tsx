import { useNavigate } from 'react-router-dom'
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
      <button className="btn primary big" onClick={() => navigate('/')}>
        Back to home
      </button>
    </main>
  )
}
