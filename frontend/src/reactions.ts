// Must match REACTION_IDS in app/routers/ws_rooms.py; the server rejects anything else.
export const REACTIONS: { id: string; label: string; kind: 'emoji' | 'phrase' }[] = [
  { id: 'laugh', label: '😂', kind: 'emoji' },
  { id: 'fire', label: '🔥', kind: 'emoji' },
  { id: 'grimace', label: '😬', kind: 'emoji' },
  { id: 'sick', label: '🤢', kind: 'emoji' },
  { id: 'clap', label: '👏', kind: 'emoji' },
  { id: 'facepalm', label: '🙈', kind: 'emoji' },
  { id: 'nice_one', label: 'Nice one!', kind: 'phrase' },
  { id: 'oh_no', label: 'Oh no…', kind: 'phrase' },
  { id: 'hurry_up', label: 'Hurry up!', kind: 'phrase' },
  { id: 'oh_come_on', label: 'Oh come on!', kind: 'phrase' },
  { id: 'regret_nothing', label: 'I regret nothing', kind: 'phrase' },
  { id: 'gg', label: 'GG', kind: 'phrase' },
]

export const REACTION_BY_ID = new Map(REACTIONS.map((r) => [r.id, r]))
export const REACTION_COOLDOWN_MS = 2000
export const REACTION_SHOW_MS = 2500
