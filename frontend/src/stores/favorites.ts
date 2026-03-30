import { defineStore } from "pinia"
import { ref, computed } from "vue"
import { favoritesApi } from "@/api/favorites"

export const useFavoritesStore = defineStore("favorites", () => {
  // State
  const favoriteDeviceNames = ref<string[]>([])
  const isLoaded = ref(false)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Actions
  async function loadFavorites(forceRefresh = false) {
    if (isLoaded.value && !forceRefresh) return

    loading.value = true
    error.value = null

    try {
      favoriteDeviceNames.value = await favoritesApi.getAll()
      isLoaded.value = true
    } catch (e) {
      const errMsg = e instanceof Error ? e.message : "Failed to load favorites"
      error.value = errMsg
      console.error("[FavoritesStore] Failed to load favorites:", e)
      favoriteDeviceNames.value = []
      isLoaded.value = true
      throw e
    } finally {
      loading.value = false
    }
  }

  async function addFavorite(deviceName: string) {
    if (favoriteDeviceNames.value.includes(deviceName)) return

    const previous = [...favoriteDeviceNames.value]
    favoriteDeviceNames.value.push(deviceName)

    try {
      await favoritesApi.add(deviceName)
      console.log("[FavoritesStore] Added favorite:", deviceName)
    } catch (e) {
      favoriteDeviceNames.value = previous
      console.error("[FavoritesStore] Failed to add favorite:", e)
      throw e
    }
  }

  async function removeFavorite(deviceName: string) {
    const index = favoriteDeviceNames.value.indexOf(deviceName)
    if (index === -1) return

    const previous = [...favoriteDeviceNames.value]
    favoriteDeviceNames.value.splice(index, 1)

    try {
      await favoritesApi.remove(deviceName)
      console.log("[FavoritesStore] Removed favorite:", deviceName)
    } catch (e) {
      favoriteDeviceNames.value = previous
      console.error("[FavoritesStore] Failed to remove favorite:", e)
      throw e
    }
  }

  async function toggleFavorite(deviceName: string) {
    if (isFavorite(deviceName)) {
      await removeFavorite(deviceName)
    } else {
      await addFavorite(deviceName)
    }
  }

  function isFavorite(deviceName: string): boolean {
    return favoriteDeviceNames.value.includes(deviceName)
  }

  async function clearFavorites() {
    const deviceNames = [...favoriteDeviceNames.value]
    await Promise.all(deviceNames.map((deviceName) => removeFavorite(deviceName)))
    console.log("[FavoritesStore] Cleared all favorites")
  }

  // Getters
  const favoritesCount = computed(() => favoriteDeviceNames.value.length)

  const hasFavorites = computed(() => favoriteDeviceNames.value.length > 0)

  return {
    // State
    favoriteDeviceNames,
    isLoaded,
    loading,
    error,
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
