import { useEffect, useMemo, useState } from 'react'
import { Card } from '../components/Card'
import { CardZoom, type ZoomItem } from '../components/CardZoom'
import { PlayerList } from '../components/PlayerList'
import { useCountdown } from '../hooks/useCountdown'
import { useRoomStore } from '../stores/roomStore'
import { AvatarRow, MuteButton, ReactionButton } from '../components/Reactions'
import { playSound } from '../sound/sfx'

const RESULT_SHOW_MS = 4500
const ORDINALS = ['1st', '2nd', '3rd']

export default function GameView({ meId }: { meId: string }) {
  const game = useRoomStore((s) => s.game)!
  const room = useRoomStore((s) => s.room)!
  const players = useRoomStore((s) => s.players)
  const lastResult = useRoomStore((s) => s.lastResult)
  const submitCards = useRoomStore((s) => s.submitCards)
  const pickWinner = useRoomStore((s) => s.pickWinner)
  const secondsLeft = useCountdown(game.phase_expires_at)

  // Tick through the last 5 seconds of any timed phase.
  useEffect(() => {
    if (secondsLeft !== null && secondsLeft > 0 && secondsLeft <= 5) playSound('tick', 0.5)
  }, [secondsLeft])

  const [selection, setSelection] = useState<string[]>([])
  const [played, setPlayed] = useState<{ round: string; ids: string[] } | null>(null)
  const [zoom, setZoom] = useState<{ kind: 'hand' | 'subs' | 'prompt'; index: number } | null>(null)
  const [showScores, setShowScores] = useState(false)
  const [resultVisible, setResultVisible] = useState(false)

  const isCzar = game.czar_id === meId
  const pick = game.black_card.pick
  const judging = game.status === 'judging'
  const playedIds = useMemo(() => (played?.round === game.round_id ? played.ids : []), [played, game.round_id])
  const hasSubmitted = game.has_submitted || game.submitted_player_ids.includes(meId) || playedIds.length > 0
  const canPlay = !isCzar && !judging && !hasSubmitted
  const hand = useMemo(() => game.hand_cards.filter((c) => !playedIds.includes(c.id)), [game.hand_cards, playedIds])
  const czar = players.find((p) => p.player_id === game.czar_id)

  // A new round clears any half-made selection and the open viewer.
  useEffect(() => {
    setSelection([])
    setZoom(null)
  }, [game.round_id])

  // Switching to judging swaps what the viewer shows, so close it.
  useEffect(() => {
    setZoom((z) => (z?.kind === 'hand' && judging ? null : z))
  }, [judging])

  useEffect(() => {
    if (!lastResult) return
    setResultVisible(true)
    const id = window.setTimeout(() => setResultVisible(false), RESULT_SHOW_MS)
    return () => window.clearTimeout(id)
  }, [lastResult])

  function play(ids: string[]) {
    playSound('play')
    submitCards(ids)
    setPlayed({ round: game.round_id, ids })
    setSelection([])
    setZoom(null)
  }

  function toggleSelect(id: string) {
    setSelection((sel) => (sel.includes(id) ? sel.filter((x) => x !== id) : sel.length < pick ? [...sel, id] : sel))
  }

  const handItems: ZoomItem[] = hand.map((c) => ({
    key: c.id,
    render: () => {
      const order = selection.indexOf(c.id)
      return <Card kind="white" text={c.text} size="full" selected={order >= 0} badge={order >= 0 ? order + 1 : null} />
    },
  }))

  const submissions = game.submissions ?? []
  const subItems: ZoomItem[] = submissions.map((s) => ({
    key: s.submission_id,
    render: () => <SubmissionStack texts={s.white_card_texts} size="full" />,
  }))

  let status: string
  if (judging) status = isCzar ? 'Pick the funniest answer' : `${czar?.username ?? 'The judge'} is choosing…`
  else if (isCzar) status = `You're the judge. Waiting for answers (${game.submitted_count}/${game.required_count})`
  else if (hasSubmitted) status = `Played! Waiting for others (${game.submitted_count}/${game.required_count})`
  else status = pick > 1 ? `Choose ${pick} cards in order` : 'Tap a card to look, then play it'

  return (
    <main className="screen game">
      <header className="game-top">
        <span className="round-label">
          Round {game.round_number}
          <span className={secondsLeft !== null && secondsLeft <= 10 ? 'timer urgent' : 'timer'}>
            {secondsLeft !== null ? `${secondsLeft}s` : ''}
          </span>
        </span>
        <div className="top-actions">
          <MuteButton />
          <ReactionButton />
          <button className="btn ghost small" onClick={() => setShowScores(true)}>
            Scores
          </button>
        </div>
      </header>

      <AvatarRow
        players={players}
        meId={meId}
        czarId={game.czar_id}
        submittedIds={judging ? [] : game.submitted_player_ids}
      />

      <section className="prompt-area">
        <Card
          kind="black"
          text={game.black_card.text}
          pick={pick}
          size="wide"
          onClick={() => setZoom({ kind: 'prompt', index: 0 })}
          label="Zoom the prompt card"
        />
        <p className="status">{status}</p>
      </section>

      {judging ? (
        <section className="submissions">
          {submissions.map((s, i) => (
            <button
              key={s.submission_id}
              className="submission-btn"
              onClick={() => setZoom({ kind: 'subs', index: i })}
              aria-label={`Answer ${i + 1}: ${s.white_card_texts.join(' / ')}`}
            >
              <SubmissionStack texts={s.white_card_texts} size="mini" />
            </button>
          ))}
        </section>
      ) : (
        <div className="grow" />
      )}

      {!judging && (
        <section className={isCzar || hasSubmitted ? 'hand muted-hand' : 'hand'} aria-label="Your hand">
          <div className="hand-row">
            {hand.map((c, i) => {
              const order = selection.indexOf(c.id)
              return (
                <Card
                  key={c.id}
                  kind="white"
                  text={c.text}
                  size="mini"
                  selected={order >= 0}
                  badge={order >= 0 ? order + 1 : null}
                  onClick={() => setZoom({ kind: 'hand', index: i })}
                />
              )
            })}
          </div>
          {canPlay && pick > 1 && (
            <button
              className="btn primary big"
              disabled={selection.length !== pick}
              onClick={() => play(selection)}
            >
              {selection.length === pick ? `Play ${pick} cards` : `Selected ${selection.length}/${pick}`}
            </button>
          )}
        </section>
      )}

      {zoom?.kind === 'prompt' && (
        <CardZoom
          items={[{ key: 'prompt', render: () => <Card kind="black" text={game.black_card.text} pick={pick} size="full" /> }]}
          startIndex={0}
          onClose={() => setZoom(null)}
          renderActions={() => null}
        />
      )}

      {zoom?.kind === 'hand' && (
        <CardZoom
          items={handItems}
          startIndex={Math.min(zoom.index, handItems.length - 1)}
          onClose={() => setZoom(null)}
          header={<Card kind="black" text={game.black_card.text} pick={pick} size="mini" />}
          renderActions={(i) => {
            const card = hand[i]
            if (!canPlay) return <p className="muted">{isCzar ? "You're judging this round." : 'You already played.'}</p>
            if (pick === 1) {
              return (
                <button className="btn primary big" onClick={() => play([card.id])}>
                  Play this card
                </button>
              )
            }
            const order = selection.indexOf(card.id)
            const full = selection.length === pick
            return (
              <div className="row">
                <button className="btn secondary grow" onClick={() => toggleSelect(card.id)} disabled={order < 0 && full}>
                  {order >= 0 ? `Unselect (${ORDINALS[order] ?? order + 1})` : `Select as ${ORDINALS[selection.length] ?? ''}`}
                </button>
                {full && (
                  <button className="btn primary grow" onClick={() => play(selection)}>
                    Play {pick}
                  </button>
                )}
              </div>
            )
          }}
        />
      )}

      {zoom?.kind === 'subs' && judging && (
        <CardZoom
          items={subItems}
          startIndex={Math.min(zoom.index, subItems.length - 1)}
          onClose={() => setZoom(null)}
          header={<Card kind="black" text={game.black_card.text} pick={pick} size="mini" />}
          renderActions={(i) =>
            isCzar ? (
              <button
                className="btn primary big"
                onClick={() => {
                  pickWinner(submissions[i].submission_id)
                  setZoom(null)
                }}
              >
                Pick this one
              </button>
            ) : (
              <p className="muted">The judge is choosing…</p>
            )
          }
        />
      )}

      {showScores && (
        <div className="sheet" role="dialog" aria-modal="true">
          <div className="zoom-backdrop" onClick={() => setShowScores(false)} />
          <div className="sheet-body panel">
            <h2>
              Scores <span className="muted">first to {room.winning_score}</span>
            </h2>
            <PlayerList
              players={players}
              hostId={room.host_id}
              meId={meId}
              czarId={game.czar_id}
              submittedIds={judging ? [] : game.submitted_player_ids}
              showScores
            />
            <button className="btn secondary" onClick={() => setShowScores(false)}>
              Close
            </button>
          </div>
        </div>
      )}

      {resultVisible && lastResult && <RoundResultOverlay meId={meId} onClose={() => setResultVisible(false)} />}
    </main>
  )
}

export function SubmissionStack({ texts, size }: { texts: string[]; size: 'mini' | 'full' }) {
  return (
    <div className={`stack-cards n${texts.length} ${size}`}>
      {texts.map((t, i) => (
        <Card key={i} kind="white" text={t} size={size} badge={texts.length > 1 ? i + 1 : null} />
      ))}
    </div>
  )
}

export function RoundResultOverlay({ meId, onClose }: { meId: string; onClose: () => void }) {
  const lastResult = useRoomStore((s) => s.lastResult)!
  const players = useRoomStore((s) => s.players)
  const winner = players.find((p) => p.player_id === lastResult.winner_player_id)
  const name = lastResult.winner_player_id === meId ? 'You' : (winner?.username ?? 'Someone who left')
  return (
    <div className="result" role="status" onClick={onClose}>
      <div className="result-body">
        <p className="result-title">{name} won the round!</p>
        {lastResult.black_card_text && <Card kind="black" text={lastResult.black_card_text} size="wide" />}
        {lastResult.winning_texts.length > 0 && <SubmissionStack texts={lastResult.winning_texts} size="full" />}
        <p className="hint">Tap to continue</p>
      </div>
    </div>
  )
}
