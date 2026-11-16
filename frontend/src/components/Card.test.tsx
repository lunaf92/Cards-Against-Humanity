import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Card } from './Card'

describe('Card', () => {
  it('renders blanks and the pick count on prompts', () => {
    const { container } = render(<Card kind="black" text="I drink to forget ___ and ___." pick={2} />)
    expect(container.querySelectorAll('.blank')).toHaveLength(2)
    expect(screen.getByText('Pick 2')).toBeInTheDocument()
  })
})
