import test from 'node:test'
import assert from 'node:assert/strict'
import { interfaceScale, appearanceStyles } from '../src/features/settings/appearance.ts'
import { boundedGeometry, defaultGeometry } from '../src/features/collaborator/windowGeometry.ts'
import { contrast, paletteReadability, paletteStyles, defaultPalette, validPalette } from '../src/features/settings/palette.ts'

test('legacy fractional interface pixels retain their exact rendered size', () => {
  for (const pixels of [14, 16, 16.5, 17, 20]) {
    const old = { interfaceSize:pixels, fontSize:17, theme:'ink', reducedMotion:false }
    assert.equal(interfaceScale(old),pixels / 16 * 100)
    assert.equal(Number.parseFloat(appearanceStyles(old)['--interface-size']),pixels)
  }
  assert.equal(interfaceScale({interfaceScale:200,interfaceSize:16}),200)
  assert.equal(interfaceScale({interfaceScale:NaN}),100)
  assert.equal(interfaceScale({interfaceScale:250}),200)
})

test('off-screen saved windows and extreme sizes remain reachable after viewport changes', () => {
  for (const viewport of [{width:1440,height:900},{width:1024,height:768},{width:390,height:844}]) {
    const result = boundedGeometry({...defaultGeometry,left:9000,top:-9000,width:4000,height:4000},viewport)
    assert.ok(result.left>=12 && result.top>=12)
    assert.ok(result.left+result.width<=viewport.width-12)
    assert.ok(result.top+result.height<=viewport.height-12)
    assert.deepEqual(boundedGeometry(result,viewport),result)
  }
})

test('palette readability rejects unusable colors and derives contrasting button text', () => {
  assert.equal(contrast('#000000','#ffffff'),21)
  assert.equal(paletteReadability(defaultPalette).valid,true)
  assert.equal(paletteReadability({...defaultPalette,text:defaultPalette.surface}).valid,false)
  assert.equal(paletteReadability({...defaultPalette,accent:'invalid'}).valid,false)
  for (const malformed of [null, {}, {text:'#ffffff'}, {accent:24}, []]) {
    assert.equal(validPalette(malformed),false)
    assert.deepEqual(paletteStyles(malformed),paletteStyles(defaultPalette))
  }
  for (const accent of ['#000000','#ffffff','#cc3333','#00ffff']) {
    const styles = paletteStyles({...defaultPalette,accent})
    assert.ok(contrast(accent,styles['--on-accent'])>=4.5)
  }
})

test('invalid persisted window dimensions fall back to usable values', () => {
  for (const value of [null, {}, {...defaultGeometry, width:NaN, height:Infinity, top:'bad'}]) {
    assert.deepEqual(boundedGeometry(value,{width:1440,height:900}),defaultGeometry)
  }
})
