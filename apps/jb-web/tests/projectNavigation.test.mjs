import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('../src/projectNavigation.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 } }).outputText
const { nextProjectAction, projectUrl, packageIndex } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
const base = { id: 'one', status: 'parsed', confirmed: false, outcome: '', results: {} }

test('primary action follows actual results instead of the furthest historical stage', () => {
  assert.equal(nextProjectAction({ ...base, stage: 'reviewed' }).route, 'trm')
  assert.equal(nextProjectAction({ ...base, confirmed: true }).route, 'workbench')
  assert.equal(nextProjectAction({ ...base, status: 'parsing' }).route, '')
  assert.equal(nextProjectAction({ ...base, outcome: 'won' }).route, '')
})

test('another package or company cannot supply the selected package progress', () => {
  const project = { ...base, confirmed: true, results: { qualify: { profile: '甲' }, generate: { A: { profile: '甲' } } } }
  assert.equal(nextProjectAction(project, { resultKey: 'A', profile: '甲' }).view, 'review')
  assert.equal(nextProjectAction(project, { resultKey: 'B', profile: '甲' }).view, 'prepare')
  assert.equal(nextProjectAction(project, { resultKey: 'A', profile: '乙' }).view, 'prepare')
})

test('navigation preserves encoded company, package and review location', () => {
  const url = new URL(projectUrl('one', 'workbench', { profile: '甲&乙 公司', pkgIndex: 2 }, 'review'), 'http://localhost')
  assert.equal(url.pathname, '/projects/one/workbench')
  assert.equal(url.searchParams.get('profile'), '甲&乙 公司')
  assert.equal(url.searchParams.get('pkg'), '2')
  assert.equal(url.searchParams.get('view'), 'review')
  for (const invalid of ['-1', 'NaN', '1.5', 'Infinity', '9']) assert.equal(packageIndex(invalid, 3), 0)
  assert.equal(packageIndex('2', 3), 2)
})
