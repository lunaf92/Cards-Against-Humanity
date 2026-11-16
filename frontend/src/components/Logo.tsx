// Two overlapping cards as a wordmark; deliberately generic, not any published game's branding.
export function Logo({ small = false }: { small?: boolean }) {
  return (
    <div className={small ? 'logo small' : 'logo'} aria-label="Cards Against Humanity clone">
      <span className="logo-card black">Cards</span>
      <span className="logo-card white">vs. Us</span>
    </div>
  )
}
