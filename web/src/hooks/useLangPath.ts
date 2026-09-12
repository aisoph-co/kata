import { useParams } from 'react-router-dom'
import { DEFAULT_LANGUAGE, isLanguage } from '@/i18n'

/** Builds an absolute path prefixed with the current `/:lang` segment, so
 * in-app links and imperative navigation survive a language switch and
 * never drop back to an unprefixed route. */
export function useLangPath() {
  const { lang } = useParams()
  const prefix = isLanguage(lang) ? lang : DEFAULT_LANGUAGE
  return (path: string) => `/${prefix}${path.startsWith('/') ? path : `/${path}`}`
}
