import { defineStore } from "pinia"
import { ref, watch } from "vue"

export type ThemeMode = "light" | "dark" | "system"

const THEME_STORAGE_KEY = "downtown-theme"

export const useThemeStore = defineStore("theme", () => {
  // State
  const theme = ref<ThemeMode>("light")
  const isLoaded = ref(false)

  // Computed dark mode status
  function isDarkMode(): boolean {
    if (theme.value === "dark") return true
    if (theme.value === "light") return false
    // System mode
    return window.matchMedia("(prefers-color-scheme: dark)").matches
  }

  // Actions
  function loadTheme() {
    try {
      const stored = localStorage.getItem(THEME_STORAGE_KEY) as ThemeMode | null
      if (stored && ["light", "dark", "system"].includes(stored)) {
        theme.value = stored
      }
      isLoaded.value = true
    } catch (e) {
      console.error("[ThemeStore] Failed to load theme from localStorage:", e)
      isLoaded.value = true
    }
  }

  function saveTheme() {
    try {
      localStorage.setItem(THEME_STORAGE_KEY, theme.value)
      applyTheme()
    } catch (e) {
      console.error("[ThemeStore] Failed to save theme to localStorage:", e)
    }
  }

  function applyTheme() {
    const html = document.documentElement
    if (isDarkMode()) {
      html.classList.add("dark")
    } else {
      html.classList.remove("dark")
    }
  }

  function setTheme(newTheme: ThemeMode) {
    theme.value = newTheme
    saveTheme()
  }

  function toggleDarkMode() {
    if (theme.value === "dark") {
      setTheme("light")
    } else {
      setTheme("dark")
    }
  }

  // Watch for system preference changes when in system mode
  if (typeof window !== "undefined") {
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)")
    mediaQuery.addEventListener("change", () => {
      if (theme.value === "system") {
        applyTheme()
      }
    })
  }

  // Watch theme changes
  watch(() => theme.value, () => {
    applyTheme()
  })

  return {
    // State
    theme,
    isLoaded,
    // Getters
    isDarkMode,
    // Actions
    loadTheme,
    setTheme,
    toggleDarkMode,
    applyTheme,
  }
})
