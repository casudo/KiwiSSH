import { defineStore } from "pinia"
import { ref, computed } from "vue"

const FAVORITES_STORAGE_KEY = "downtown-favorites"

export const useFavoritesStore = defineStore("favorites", () => {
  // State - stored as array of device names
  const favoriteDeviceNames = ref<string[]>([])
  const isLoaded = ref(false)

  // Actions
  function loadFavorites() {
    try {
      const stored = localStorage.getItem(FAVORITES_STORAGE_KEY)
      if (stored) {
        favoriteDeviceNames.value = JSON.parse(stored)
      }
      isLoaded.value = true
    } catch (e) {
      console.error("[FavoritesStore] Failed to load favorites from localStorage:", e)
      favoriteDeviceNames.value = []
      isLoaded.value = true
    }
  }

  function saveFavorites() {
    try {
      localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(favoriteDeviceNames.value))
    } catch (e) {
      console.error("[FavoritesStore] Failed to save favorites to localStorage:", e)
    }
  }

  function addFavorite(deviceName: string) {
    if (!favoriteDeviceNames.value.includes(deviceName)) {
      favoriteDeviceNames.value.push(deviceName)
      saveFavorites()
      console.log("[FavoritesStore] Added favorite:", deviceName)
    }
  }

  function removeFavorite(deviceName: string) {
    const index = favoriteDeviceNames.value.indexOf(deviceName)
    if (index !== -1) {
      favoriteDeviceNames.value.splice(index, 1)
      saveFavorites()
      console.log("[FavoritesStore] Removed favorite:", deviceName)
    }
  }

  function toggleFavorite(deviceName: string) {
    if (isFavorite(deviceName)) {
      removeFavorite(deviceName)
    } else {
      addFavorite(deviceName)
    }
  }

  function isFavorite(deviceName: string): boolean {
    return favoriteDeviceNames.value.includes(deviceName)
  }

  function clearFavorites() {
    favoriteDeviceNames.value = []
    saveFavorites()
    console.log("[FavoritesStore] Cleared all favorites")
  }

  // Getters
  const favoritesCount = computed(() => favoriteDeviceNames.value.length)

  const hasFavorites = computed(() => favoriteDeviceNames.value.length > 0)

  return {
    // State
    favoriteDeviceNames,
    isLoaded,
    // Getters
    favoritesCount,
    hasFavorites,
    // Actions
    loadFavorites,
    addFavorite,
    removeFavorite,
    toggleFavorite,
    isFavorite,
    clearFavorites,
  }
})
