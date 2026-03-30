<script setup>
import { onMounted } from "vue"
import Navbar from "@/components/Navbar.vue"
import Footer from "@/components/Footer.vue"
import { useFavoritesStore } from "@/stores/favorites"
import { useThemeStore } from "@/stores/theme"

const favoritesStore = useFavoritesStore()
const themeStore = useThemeStore()

onMounted(async () => {
  // Load theme
  if (!themeStore.isLoaded) {
    themeStore.loadTheme()
    themeStore.applyTheme()
  }

  // Load favorites
  if (!favoritesStore.isLoaded) {
    try {
      await favoritesStore.loadFavorites()
    } catch (e) {
      console.warn("Failed to load favorites from backend:", e)
    }
  }
})
</script>

<template>
  <div class="min-h-screen bg-gray-50 dark:bg-gray-900 flex flex-col transition-colors">
    <Navbar />
    <main class="container mx-auto px-4 py-8 flex-grow">
      <RouterView />
    </main>
    <Footer />
  </div>
</template>
