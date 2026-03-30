<script setup lang="ts">
import { computed, ref } from "vue"
import StatusBadge from "./StatusBadge.vue"
import { backupApi } from "@/api/backups"
import { useFavoritesStore } from "@/stores/favorites"
import type { Device } from "@/types/device"

const props = defineProps<{
  device: Device
}>()

const favoritesStore = useFavoritesStore()
const triggering = ref(false)
const isFavorite = computed(() => favoritesStore.isFavorite(props.device.device_name))

async function handleToggleFavorite(e: Event) {
  e.stopPropagation()
  try {
    await favoritesStore.toggleFavorite(props.device.device_name)
  } catch (error) {
    console.error("Failed to toggle favorite:", error)
  }
}

async function handleTriggerBackup(e: Event) {
  e.stopPropagation()

  if (triggering.value) return
  triggering.value = true

  try {
    await backupApi.triggerDevice(props.device.device_name)
  } catch (error) {
    console.error("Failed to trigger backup:", error)
  } finally {
    triggering.value = false
  }
}
</script>

<template>
  <div class="card-hover p-4">
    <div class="flex items-start justify-between gap-2">
      <div class="flex-1 min-w-0">
        <h3 class="text-sm font-semibold text-gray-900 truncate">
          {{ device.device_name }}
        </h3>
        <p class="text-xs text-gray-500 font-mono truncate">{{ device.ip_address }}</p>
      </div>
      <div class="flex items-center gap-1 flex-shrink-0">
        <button
          @click="handleToggleFavorite"
          class="px-1.5 py-0.5 text-xs rounded transition border"
          :class="isFavorite ? 'bg-amber-100 text-amber-700 border-amber-200 hover:bg-amber-200' : 'bg-gray-100 text-gray-500 border-gray-200 hover:bg-gray-200'"
          :title="isFavorite ? 'Remove from favorites' : 'Add to favorites'"
          :aria-label="isFavorite ? 'Remove from favorites' : 'Add to favorites'"
        >
          {{ isFavorite ? "★" : "☆" }}
        </button>
        <StatusBadge :status="device.status" />
        <button
          @click="handleTriggerBackup"
          :disabled="triggering"
          class="px-1.5 py-0.5 text-xs bg-downtown-100 text-downtown-700 hover:bg-downtown-200 rounded transition"
          title="Trigger backup"
        >
          {{ triggering ? "..." : "▶" }}
        </button>
      </div>
    </div>
  </div>
</template>
