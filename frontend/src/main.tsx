import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App'
import { installAudioUnlock } from './sound/sfx'

installAudioUnlock()

createRoot(document.getElementById('root')!).render(
  // No StrictMode: its double-run effects would join and leave the matchmaking queue twice.
  <BrowserRouter>
    <App />
  </BrowserRouter>,
)
