import { fireEvent, render, screen } from '@testing-library/react'
import axe from 'axe-core'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { Modal } from '../src/components/Ui'

function ModalHarness() {
  const [open, setOpen] = useState(false)
  return <><button onClick={() => setOpen(true)}>Open dialog</button>{open && <Modal title="Accessible dialog" onClose={() => setOpen(false)}><button>Finish</button></Modal>}</>
}

describe('Modal accessibility', () => {
  it('passes an automated axe accessibility smoke check', async () => {
    const { container } = render(<Modal title="Accessible dialog" onClose={() => undefined}><button>Finish</button></Modal>)
    const results = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } })
    expect(results.violations.map((violation) => violation.id)).toEqual([])
  })

  it('labels the dialog, closes with Escape, and restores trigger focus', () => {
    render(<ModalHarness />)
    const trigger = screen.getByRole('button', { name: 'Open dialog' })
    trigger.focus()
    fireEvent.click(trigger)

    const dialog = screen.getByRole('dialog', { name: 'Accessible dialog' })
    expect(dialog).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Close' })).toHaveFocus()

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('keeps Tab navigation inside the dialog', () => {
    render(<ModalHarness />)
    fireEvent.click(screen.getByRole('button', { name: 'Open dialog' }))
    const close = screen.getByRole('button', { name: 'Close' })
    const finish = screen.getByRole('button', { name: 'Finish' })

    finish.focus()
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(close).toHaveFocus()

    close.focus()
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(finish).toHaveFocus()
  })
})
