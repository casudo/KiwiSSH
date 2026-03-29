<script setup lang="ts">
import { RouterLink, useRoute } from "vue-router"
import { useThemeStore } from "@/stores/theme"
import { computed } from "vue"
import { APP_VERSION } from "@/version"

const route = useRoute()
const themeStore = useThemeStore()

interface NavItem {
  name: string
  path: string
}

const navItems: NavItem[] = [
  { name: "Dashboard", path: "/" },
  { name: "Devices", path: "/devices" },
  { name: "Vendors", path: "/vendors" },
  { name: "Groups", path: "/groups" },
  { name: "SSH Profiles", path: "/ssh-profiles" },
  { name: "Jobs", path: "/jobs" },
  { name: "Settings", path: "/settings" },
]

const isActive = (path: string): boolean => {
  if (path === "/") return route.path === "/"
  return route.path.startsWith(path)
}

const isDarkMode = computed(() => themeStore.isDarkMode())
</script>

<template>
  <nav class="bg-downtown-800 dark:bg-gray-800 text-white shadow-lg transition-colors">
    <div class="container mx-auto px-4">
      <div class="flex items-center justify-between h-16">
        <!-- Logo -->
        <RouterLink to="/" class="flex items-center space-x-3">
          <div class="w-8 h-8 bg-downtown-500 rounded-lg flex items-center justify-center">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M2 5a2 2 0 012-2h12a2 2 0 012 2v10a2 2 0 01-2 2H4a2 2 0 01-2-2V5zm3.293 1.293a1 1 0 011.414 0l3 3a1 1 0 010 1.414l-3 3a1 1 0 01-1.414-1.414L7.586 10 5.293 7.707a1 1 0 010-1.414zM11 12a1 1 0 100 2h3a1 1 0 100-2h-3z" clip-rule="evenodd" />
            </svg>
          </div>
          <span class="text-xl font-bold">Downtown</span>
          <span class="text-sm text-downtown-300 dark:text-gray-400">v{{ APP_VERSION }}</span>
        </RouterLink>

        <!-- Navigation and Theme Toggle -->
        <div class="flex items-center space-x-1">
          <RouterLink
            v-for="item in navItems"
            :key="item.path"
            :to="item.path"
            class="px-4 py-2 rounded-md text-sm font-medium transition-colors"
            :class="isActive(item.path)
              ? 'bg-downtown-900 dark:bg-gray-900 text-white'
              : 'text-downtown-100 dark:text-gray-300 hover:bg-downtown-700 dark:hover:bg-gray-700 hover:text-white'"
          >
            {{ item.name }}
          </RouterLink>

          <!-- Theme Toggle Button -->
          <button
            @click="themeStore.toggleDarkMode()"
            class="px-3 py-2 ml-2 rounded-md text-sm font-medium transition-colors text-downtown-100 dark:text-gray-300 hover:bg-downtown-700 dark:hover:bg-gray-700 hover:text-white"
            :title="isDarkMode ? 'Switch to light mode' : 'Switch to dark mode'"
          >
            <span v-if="isDarkMode" class="text-lg">☀️</span>
            <span v-else class="text-lg">🌙</span>
          </button>
        </div>
      </div>
    </div>
  </nav>
</template>
