import type { Player } from '../api/types'
import { useCountdown } from '../hooks/useCountdown'
import { useRoomStore } from '../stores/roomStore'
import { ReactionBubble } from './Reactions'

interface Props {
  players: Player[]
  hostId: string | null
  meId: string
  czarId?: string
  submittedIds?: string[]
  showScores?: boolean
}

export function PlayerList({ players, hostId, meId, czarId, submittedIds, showScores }: Props) {
  const sorted = [...players].sort((a, b) =>
    showScores ? b.score - a.score || a.join_order - b.join_order : a.join_order - b.join_order,
  )
  return (
    <ul className="players">
      {sorted.map((p) => (
        <PlayerRow
          key={p.player_id}
          player={p}
          isHost={p.player_id === hostId}
          isMe={p.player_id === meId}
          isCzar={p.player_id === czarId}
          submitted={submittedIds?.includes(p.player_id) ?? false}
          showScore={!!showScores}
        />
      ))}
    </ul>
  )
}

function PlayerRow({
  player,
  isHost,
  isMe,
  isCzar,
  submitted,
  showScore,
}: {
  player: Player
  isHost: boolean
  isMe: boolean
  isCzar: boolean
  submitted: boolean
  showScore: boolean
}) {
  const deadline = useRoomStore((s) => s.reconnectDeadlines[player.player_id])
  const left = useCountdown(player.is_connected ? null : deadline)
  return (
    <li className={player.is_connected ? 'player' : 'player offline'}>
      <ReactionBubble playerId={player.player_id} />
      <span className="avatar" aria-hidden>
        {player.username.slice(0, 1).toUpperCase()}
      </span>
      <span className="player-name">
        {player.username}
        {isMe && <span className="muted"> (you)</span>}
      </span>
      <span className="badges">
        {isHost && <span className="badge">Host</span>}
        {isCzar && <span className="badge dark">Judge</span>}
        {submitted && <span className="badge ok">Played</span>}
        {!player.is_connected && <span className="badge warn">{left !== null ? `Away ${left}s` : 'Away'}</span>}
      </span>
      {showScore && <span className="score">{player.score}</span>}
    </li>
  )
}
