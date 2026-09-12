import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { classifyIntent } from './insight-router.ts'

describe('classifyIntent', () => {
  it('routes the PLAN_15 self-summary phrasing to self_summary', () => {
    assert.deepEqual(classifyIntent('How am I doing?'), { kind: 'self_summary' })
    assert.deepEqual(classifyIntent('how am i doing'), { kind: 'self_summary' })
  })

  it('routes "where am I weakest" to weakest', () => {
    assert.deepEqual(classifyIntent('Where am I weakest?'), { kind: 'weakest' })
  })

  it('routes "show my mastery by concept" to mastery_chart', () => {
    assert.deepEqual(classifyIntent('show my mastery by concept'), { kind: 'mastery_chart' })
    assert.deepEqual(classifyIntent('Can I get a mastery chart?'), { kind: 'mastery_chart' })
  })

  it('routes a p_known/trend question to trend_chart', () => {
    assert.deepEqual(classifyIntent('show my p_known over the last 30 days'), { kind: 'trend_chart' })
    assert.deepEqual(classifyIntent("what's my progress trend"), { kind: 'trend_chart' })
  })

  it('routes "what should I review" to next_review', () => {
    assert.deepEqual(classifyIntent('What should I review?'), { kind: 'next_review' })
    assert.deepEqual(classifyIntent('quiz me'), { kind: 'next_review' })
  })

  it('routes a team question to team_summary', () => {
    assert.deepEqual(classifyIntent('how is my team doing?'), { kind: 'team_summary' })
  })

  it('routes a named-other-person question to person_summary with the roster id', () => {
    const intent = classifyIntent('how is Hugo doing?')
    assert.equal(intent?.kind, 'person_summary')
    if (intent?.kind === 'person_summary') {
      assert.equal(intent.person.firstName, 'hugo')
      assert.equal(intent.person.personId, 'bd33e37f-cc6e-537a-99af-e01daae77bea')
    }
  })

  it('leaves an ordinary conversational turn unmatched (Hermes lane)', () => {
    assert.equal(classifyIntent('thanks, that helps'), null)
    assert.equal(classifyIntent('what is idempotency, in one sentence?'), null)
    assert.equal(classifyIntent(''), null)
  })
})
