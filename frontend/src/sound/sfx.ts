import { create } from 'zustand'

export type SoundName =
  | 'play'
  | 'zoom'
  | 'all_in'
  | 'judge'
  | 'round'
  | 'round_win'
  | 'tick'
  | 'reaction'
  | 'game_over'

const NAMES: SoundName[] = ['play', 'zoom', 'all_in', 'judge', 'round', 'round_win', 'tick', 'reaction', 'game_over']
const MUTE_KEY = 'cah.muted'

function readMuted(): boolean {
  try {
    return localStorage.getItem(MUTE_KEY) === '1'
  } catch {
    return false
  }
}

// Mute preference, remembered per device.
export const useSoundSettings = create<{ muted: boolean; toggle: () => void }>((set, get) => ({
  muted: readMuted(),
  toggle() {
    const muted = !get().muted
    try {
      localStorage.setItem(MUTE_KEY, muted ? '1' : '0')
    } catch {
      /* preference lasts for this page only */
    }
    set({ muted })
    if (!muted) unlock()
  },
}))

let ctx: AudioContext | null = null
const buffers = new Map<SoundName, AudioBuffer>()
let loading: Promise<void> | null = null

function context(): AudioContext | null {
  if (ctx) return ctx
  const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!Ctor) return null
  ctx = new Ctor()
  return ctx
}

// Decode every effect once; files live in public/sounds and can be swapped for recorded ones.
function load(): Promise<void> {
  if (loading) return loading
  const ac = context()
  if (!ac) return Promise.resolve()
  loading = Promise.all(
    NAMES.map(async (name) => {
      try {
        const res = await fetch(`/sounds/${name}.wav`)
        buffers.set(name, await ac.decodeAudioData(await res.arrayBuffer()))
      } catch {
        /* a missing sound just stays silent */
      }
    }),
  ).then(() => undefined)
  return loading
}

// Browsers only allow audio after a user gesture: resume on the first tap anywhere.
export function unlock() {
  const ac = context()
  if (!ac) return
  if (ac.state === 'suspended') void ac.resume()
  void load()
}

export function installAudioUnlock() {
  const handler = () => {
    unlock()
    window.removeEventListener('pointerdown', handler)
    window.removeEventListener('keydown', handler)
  }
  window.addEventListener('pointerdown', handler)
  window.addEventListener('keydown', handler)
}

export function playSound(name: SoundName, volume = 0.8) {
  if (useSoundSettings.getState().muted) return
  const ac = context()
  const buffer = buffers.get(name)
  if (!ac || !buffer || ac.state !== 'running') return
  const source = ac.createBufferSource()
  const gain = ac.createGain()
  gain.gain.value = volume
  source.buffer = buffer
  source.connect(gain).connect(ac.destination)
  source.start()
}

// Short buzz on phones that support it (Android browsers; iOS Safari ignores it).
export function vibrate(pattern: number | number[]) {
  if (useSoundSettings.getState().muted) return
  try {
    navigator.vibrate?.(pattern)
  } catch {
    /* unsupported */
  }
}
