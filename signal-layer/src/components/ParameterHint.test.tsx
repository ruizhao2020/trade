import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ParameterHint } from './ParameterHint.tsx'

describe('ParameterHint', () => {
  it('shows the parameter meaning after clicking the info icon and closes outside', () => {
    render(<div><ParameterHint label="周期" text="用于计算的K线数量。" /><span data-testid="outside">外部</span></div>)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '周期说明' }))
    expect(screen.getByRole('tooltip')).toHaveTextContent('用于计算的K线数量。')
    fireEvent.pointerDown(screen.getByTestId('outside'))
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })
})
