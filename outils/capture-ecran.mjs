// Capture d'écran de l'interface sans l'extension Chrome : Edge headless piloté par le protocole DevTools.
// (Repris du projet Bible annotée.) Le serveur de développement doit tourner : python -m outils.serveur_dev
//
// Usage : node outils/capture-ecran.mjs <nom> <largeur> <hauteur> [attenteMs] [script]
//   script : JavaScript exécuté avant la capture (une promesse est attendue), ex. ouvrir la boîte d'import.
// Autre adresse : variable APP (défaut http://localhost:8765).
// Les images vont dans le dossier temporaire de Windows (lecteur-captures), jamais dans le projet.
import { spawn } from 'node:child_process'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const [nom, larg, haut, attente = '4000', scriptBrut = ''] = process.argv.slice(2)
// « @fichier.js » : script lu dans un fichier (PowerShell 5.1 abîme les guillemets des arguments).
const script = scriptBrut.startsWith('@') ? readFileSync(scriptBrut.slice(1), 'utf8') : scriptBrut
const dossier = join(tmpdir(), 'lecteur-captures')
mkdirSync(dossier, { recursive: true })
const port = 9334
const edge = spawn('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', [
  '--headless=new',
  `--remote-debugging-port=${port}`,
  `--user-data-dir=${join(dossier, 'profil')}`,
  `--window-size=${larg},${haut}`,
  'about:blank'
])
const pause = (ms) => new Promise((r) => setTimeout(r, ms))
let cibles = []
for (let i = 0; i < 50; i++) {
  try {
    cibles = await (await fetch(`http://127.0.0.1:${port}/json`)).json()
    if (cibles.some((c) => c.type === 'page')) break
  } catch {
    // Edge n'est pas encore prêt
  }
  await pause(200)
}
const page = cibles.find((c) => c.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
await new Promise((r) => ws.addEventListener('open', r))
let id = 0
const attentes = new Map()
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data)
  if (m.id && attentes.has(m.id)) attentes.get(m.id)(m)
  if (m.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(m.params.type))
    console.log('[console]', m.params.args.map((a) => a.value ?? a.description).join(' '))
  if (m.method === 'Runtime.exceptionThrown')
    console.log('[exception]', m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text)
})
const cmd = (method, params = {}) =>
  new Promise((r) => {
    const n = ++id
    attentes.set(n, r)
    ws.send(JSON.stringify({ id: n, method, params }))
  })
await cmd('Runtime.enable')
await cmd('Emulation.setDeviceMetricsOverride', { width: +larg, height: +haut, deviceScaleFactor: 1, mobile: false })
await cmd('Page.navigate', { url: process.env.APP ?? 'http://localhost:8765/' })
await pause(+attente)
if (script) {
  const r = await cmd('Runtime.evaluate', { expression: script, awaitPromise: true })
  const ex = r.result?.exceptionDetails
  console.log('[script]', JSON.stringify(r.result?.result?.value ?? ex?.exception?.description ?? ex?.text))
  await pause(1500)
}
const r = await cmd('Page.captureScreenshot', { format: 'png' })
const fichier = join(dossier, `${nom}.png`)
writeFileSync(fichier, Buffer.from(r.result.data, 'base64'))
console.log('ok', fichier)
ws.close()
edge.kill()
process.exit(0)
