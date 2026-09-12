import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { confirmRole, resetRoleConfirm, useRoleConfirm } from './role-confirm-store'

describe('role-confirm-store', () => {
  beforeEach(() => {
    resetRoleConfirm()
  })

  it('starts with no person and no role confirmed', () => {
    const { result } = renderHook(() => useRoleConfirm())
    expect(result.current).toEqual({ personId: null, role: null })
  })

  it('confirmRole records the role for that person', () => {
    const { result } = renderHook(() => useRoleConfirm())

    act(() => confirmRole('person-1', 'senior_swe'))

    expect(result.current).toEqual({ personId: 'person-1', role: 'senior_swe' })
  })

  it('resetRoleConfirm clears a prior confirmation so the next sign-in must confirm again', () => {
    const { result } = renderHook(() => useRoleConfirm())
    act(() => confirmRole('person-1', 'senior_swe'))

    act(() => resetRoleConfirm())

    expect(result.current).toEqual({ personId: null, role: null })
  })
})
