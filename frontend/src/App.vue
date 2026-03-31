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
  <div class="relative min-h-screen">
    <div class="pointer-events-none absolute inset-0 overflow-hidden">
      <div class="absolute -top-24 -left-24 h-72 w-72 rounded-full bg-downtown-200/40 blur-3xl dark:bg-downtown-900/30" />
      <div class="absolute top-1/3 -right-28 h-80 w-80 rounded-full bg-teal-200/30 blur-3xl dark:bg-teal-900/20" />
    </div>

    <div class="relative z-10 flex min-h-screen flex-col">
      <Navbar />
      <main class="container mx-auto w-full px-4 py-8 flex-grow">
        <RouterView />
      </main>
      <Footer />
    </div>
  </div>
</template>
