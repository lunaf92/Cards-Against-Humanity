import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { decksApi } from '../api/endpoints'

// Landing page for a deck share link: join as co-editor, then open the deck.
export default function JoinDeckPage() {
  const { code = '' } = useParams()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    decksApi
      .join(code)
      .then((deck) => navigate(`/decks/${deck.id}`, { replace: true }))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Could not open that link'))
  }, [code, navigate])

  return (
    <main className="screen center stack">
      {error ? (
        <>
          <p className="error">{error}</p>
          <Link className="btn secondary" to="/decks">
            Go to my decks
          </Link>
        </>
      ) : (
        <p className="muted">Opening the shared deck…</p>
      )}
    </main>
  )
}
