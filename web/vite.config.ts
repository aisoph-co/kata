import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv, type Plugin } from 'vite'

/**
 * Dev-server twin of the Caddyfile's `/__e2e/session` handler (AGCTM-64
 * finding #5): answers 200 `{"email"}` only when E2E_AUTH_BYPASS_TOKEN is
 * set here AND the request's X-E2E-Auth-Bypass header carries that exact
 * value; 404 in every other case, so an unset variable changes nothing.
 */
function e2eSessionPlugin(token: string | undefined): Plugin {
  return {
    name: 'kata-e2e-session',
    configureServer(server) {
      server.middlewares.use('/__e2e/session', (req, res) => {
        const sent = req.headers['x-e2e-auth-bypass']
        const email = req.headers['x-e2e-learner-email']
        if (token && typeof sent === 'string' && sent === token && typeof email === 'string' && email) {
          res.statusCode = 200
          res.setHeader('Content-Type', 'application/json')
          res.end(JSON.stringify({ email }))
          return
        }
        res.statusCode = 404
        res.end()
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Loaded server-side only (Vite config runs in Node, never in the bundle).
  // SERVICE_TOKEN must never be exposed via a VITE_ prefixed var.
  const env = loadEnv(mode, process.cwd(), '')
  const serviceToken = env.SERVICE_TOKEN ?? 'dev'
  const apiTarget = env.API_TARGET ?? 'http://localhost:8000'
  const e2eBypassToken = env.E2E_AUTH_BYPASS_TOKEN || undefined

  return {
    plugins: [react(), tailwindcss(), e2eSessionPlugin(e2eBypassToken)],
    resolve: {
      alias: {
        '@': new URL('./src', import.meta.url).pathname,
      },
    },
    server: {
      port: 5173,
      // AE-24 tech-lead review #4: without this, a busy 5173 (e.g.
      // `npm run demo` already running) silently binds 5174 instead, and
      // every Auth0 sign-in then dies on a callback URL mismatch — the
      // tenant only allow-lists 5173. Fail loudly instead.
      strictPort: true,
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api/, ''),
          configure: (proxy) => {
            proxy.on('proxyReq', (proxyReq) => {
              proxyReq.setHeader('Authorization', `Bearer ${serviceToken}`)
              // Same as Caddy: the e2e bypass headers never reach the core.
              proxyReq.removeHeader('X-E2E-Auth-Bypass')
              proxyReq.removeHeader('X-E2E-Learner-Email')
            })
          },
        },
      },
    },
  }
})
