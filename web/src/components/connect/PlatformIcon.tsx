import { useId } from 'react'
import { siDiscord, siTelegram, siWhatsapp } from 'simple-icons'
import type { Platform } from '@/lib/connect-store'

/**
 * Official brand marks, inline SVG, no external asset loads (CSP /
 * demo-offline rule) — fetched once and committed. Source + licence for
 * each mark is in `src/components/connect/ICONS.md`.
 *
 * Discord/Telegram/WhatsApp: `simple-icons` npm package (MIT path data).
 * Slack/Teams: current `simple-icons` ships neither (Slack's mark was
 * pulled pending the trademark owner's permission — simple-icons/simple-
 * icons#14140 — and Teams was never added), so both are downloaded
 * directly from Wikimedia Commons (PD-textlogo, still trademarked marks)
 * and inlined below instead.
 */
const SIMPLE_ICONS: Record<string, { path: string; hex: string }> = {
  discord: siDiscord,
  telegram: siTelegram,
  whatsapp: siWhatsapp,
}

/** Slack "hashtag" mark — commons.wikimedia.org/wiki/File:Slack_icon_2019.svg (PD-textlogo). */
function SlackMark({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 127 127" role="img" aria-label="Slack">
      <path
        fill="#e01e5a"
        d="M27.2 80c0 7.3-5.9 13.2-13.2 13.2S.8 87.3.8 80 6.7 66.8 14 66.8h13.2zm6.6 0c0-7.3 5.9-13.2 13.2-13.2S60.2 72.7 60.2 80v33c0 7.3-5.9 13.2-13.2 13.2s-13.2-5.9-13.2-13.2z"
      />
      <path
        fill="#36c5f0"
        d="M47 27c-7.3 0-13.2-5.9-13.2-13.2S39.7.6 47 .6s13.2 5.9 13.2 13.2V27zm0 6.7c7.3 0 13.2 5.9 13.2 13.2S54.3 60.1 47 60.1H13.9C6.6 60.1.7 54.2.7 46.9s5.9-13.2 13.2-13.2z"
      />
      <path
        fill="#2eb67d"
        d="M99.9 46.9c0-7.3 5.9-13.2 13.2-13.2s13.2 5.9 13.2 13.2-5.9 13.2-13.2 13.2H99.9zm-6.6 0c0 7.3-5.9 13.2-13.2 13.2s-13.2-5.9-13.2-13.2V13.8C66.9 6.5 72.8.6 80.1.6s13.2 5.9 13.2 13.2z"
      />
      <path
        fill="#ecb22e"
        d="M80.1 99.8c7.3 0 13.2 5.9 13.2 13.2s-5.9 13.2-13.2 13.2-13.2-5.9-13.2-13.2V99.8zm0-6.6c-7.3 0-13.2-5.9-13.2-13.2s5.9-13.2 13.2-13.2h33.1c7.3 0 13.2 5.9 13.2 13.2s-5.9 13.2-13.2 13.2z"
      />
    </svg>
  )
}

/** Microsoft Teams mark, 2019–2025 official design — commons.wikimedia.org/
 * wiki/File:Microsoft_Office_Teams_(2019–2025).svg (PD-textlogo). Used over
 * the current 2025 multi-gradient redesign (~4.1 KB even minified, a dozen
 * radial gradients) for size budget and legibility at 24–28px icon scale;
 * still an official Microsoft-published mark, just not the newest one. */
function TeamsMark({ size, gradientId }: { size: number; gradientId: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 2228.833 2073.333" role="img" aria-label="Teams">
      <path
        fill="#5059c9"
        d="M1554.637 777.5h575.713c54.391 0 98.483 44.092 98.483 98.483v524.398c0 199.901-162.051 361.952-361.952 361.952h-1.711c-199.901.028-361.975-162-362.004-361.901V828.971c.001-28.427 23.045-51.471 51.471-51.471"
      />
      <circle cx="1943.75" cy="440.583" r="233.25" fill="#5059c9" />
      <circle cx="1218.083" cy="336.917" r="336.917" fill="#7b83eb" />
      <path
        fill="#7b83eb"
        d="M1667.323 777.5H717.01c-53.743 1.33-96.257 45.931-95.01 99.676v598.105c-7.505 322.519 247.657 590.16 570.167 598.053 322.51-7.893 577.671-275.534 570.167-598.053V877.176c1.245-53.745-41.268-98.346-95.011-99.676"
      />
      <path
        opacity=".1"
        d="M1244 777.5v838.145c-.258 38.435-23.549 72.964-59.09 87.598a91.9 91.9 0 0 1-35.765 7.257H667.613c-6.738-17.105-12.958-34.21-18.142-51.833a631.3 631.3 0 0 1-27.472-183.49V877.02c-1.246-53.659 41.198-98.19 94.855-99.52z"
      />
      <path
        opacity=".2"
        d="M1192.167 777.5v889.978a91.8 91.8 0 0 1-7.257 35.765c-14.634 35.541-49.163 58.833-87.598 59.09H691.975c-8.812-17.105-17.105-34.21-24.362-51.833s-12.958-34.21-18.142-51.833a631.3 631.3 0 0 1-27.472-183.49V877.02c-1.246-53.659 41.198-98.19 94.855-99.52z"
      />
      <path
        opacity=".2"
        d="M1192.167 777.5v786.312c-.395 52.223-42.632 94.46-94.855 94.855h-447.84A631.3 631.3 0 0 1 622 1475.177V877.02c-1.246-53.659 41.198-98.19 94.855-99.52z"
      />
      <path
        opacity=".2"
        d="M1140.333 777.5v786.312c-.395 52.223-42.632 94.46-94.855 94.855H649.472A631.3 631.3 0 0 1 622 1475.177V877.02c-1.246-53.659 41.198-98.19 94.855-99.52z"
      />
      <path
        opacity=".1"
        d="M1244 509.522v163.275c-8.812.518-17.105 1.037-25.917 1.037s-17.105-.518-25.917-1.037a284.5 284.5 0 0 1-51.833-8.293c-104.963-24.857-191.679-98.469-233.25-198.003a288 288 0 0 1-16.587-51.833h258.648c52.305.198 94.657 42.549 94.856 94.854"
      />
      <path
        opacity=".2"
        d="M1192.167 561.355v111.442a284.5 284.5 0 0 1-51.833-8.293c-104.963-24.857-191.679-98.469-233.25-198.003h190.228c52.304.198 94.656 42.55 94.855 94.854"
      />
      <path
        opacity=".2"
        d="M1140.333 561.355v103.148c-104.963-24.857-191.679-98.469-233.25-198.003h138.395c52.305.199 94.656 42.551 94.855 94.855"
      />
      <defs>
        <linearGradient id={gradientId} x1="198.099" x2="942.234" y1="1683.073" y2="394.261" gradientTransform="matrix(1 0 0 -1 0 2075.333)" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#5a62c3" />
          <stop offset=".5" stopColor="#4d55bd" />
          <stop offset="1" stopColor="#3940ab" />
        </linearGradient>
      </defs>
      <path
        fill={`url(#${gradientId})`}
        d="M95.01 466.5h950.312c52.473 0 95.01 42.538 95.01 95.01v950.312c0 52.473-42.538 95.01-95.01 95.01H95.01c-52.473 0-95.01-42.538-95.01-95.01V561.51c0-52.472 42.538-95.01 95.01-95.01"
      />
      <path fill="#fff" d="M820.211 828.193h-189.97v517.297h-121.03V828.193H320.123V727.844h500.088z" />
    </svg>
  )
}

export function PlatformIcon({ platform, size = 28 }: { platform: Platform; size?: number }) {
  const gradientId = useId()

  if (platform.id === 'slack') return <SlackMark size={size} />
  if (platform.id === 'teams') return <TeamsMark size={size} gradientId={`teams-grad-${gradientId}`} />

  const brand = SIMPLE_ICONS[platform.id]
  if (!brand) return null

  return (
    <svg width={size} height={size} viewBox="0 0 24 24" role="img" aria-label={platform.name}>
      <path d={brand.path} fill={`#${brand.hex}`} />
    </svg>
  )
}
