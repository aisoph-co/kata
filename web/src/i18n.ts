import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from '@/locales/en.json'
import vi from '@/locales/vi.json'

export const SUPPORTED_LANGUAGES = ['en', 'vi'] as const
export type Language = (typeof SUPPORTED_LANGUAGES)[number]
export const DEFAULT_LANGUAGE: Language = 'en'

const STORAGE_KEY = 'demo-web.lang'

export function isLanguage(value: string | undefined | null): value is Language {
  return !!value && (SUPPORTED_LANGUAGES as readonly string[]).includes(value)
}

export function getStoredLanguage(): Language | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return isLanguage(value) ? value : null
  } catch {
    return null
  }
}

export function setStoredLanguage(lang: Language) {
  try {
    localStorage.setItem(STORAGE_KEY, lang)
  } catch {
    // private browsing / storage disabled — language just won't survive reload
  }
}

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    vi: { translation: vi },
  },
  lng: DEFAULT_LANGUAGE,
  fallbackLng: DEFAULT_LANGUAGE,
  interpolation: { escapeValue: false },
  returnNull: false,
})

export default i18n
