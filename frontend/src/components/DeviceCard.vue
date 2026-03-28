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

function handleToggleFavorite(e: Event) {
  e.stopPropagation()
  favoritesStore.toggleFavorite(props.device.device_name)
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
  <div class="card-hover">
    <div class="flex items-start justify-between">
      <div class="flex-1 min-w-0">
        <h3 class="text-lg font-semibold text-gray-900 truncate">
          {{ device.device_name }}
        </h3>
        <p class="text-sm text-gray-500 font-mono">{{ device.ip_address }}</p>
      </div>
      <div class="flex items-center gap-2 flex-shrink-0">
        <button
          @click="handleToggleFavorite"
          class="px-2 py-1 text-xs rounded transition border"
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
          class="px-2 py-1 text-xs bg-downtown-100 text-downtown-700 hover:bg-downtown-200 rounded transition"
          title="Trigger backup"
        >
          {{ triggering ? "..." : "▶" }}
        </button>
      </div>
    </div>

    <div class="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-gray-600">
      <span class="flex items-center">
        <span class="text-gray-400 mr-1">Group:</span>
        <span class="font-medium">{{ device.group }}</span>
      </span>
      <span class="flex items-center">
        <span class="text-gray-400 mr-1">Vendor:</span>
        <span class="font-medium">{{ device.vendor }}</span>
      </span>
    </div>

    <div class="mt-3 flex items-center justify-between">
      <div v-if="!device.enabled" class="text-xs text-amber-600 font-medium">
        Disabled
      </div>
      <div v-else-if="device.last_backup" class="text-xs text-gray-400">
        Last backup: {{ new Date(device.last_backup).toLocaleString() }}
      </div>
      <div v-else class="text-xs text-gray-400">
        No backups yet
      </div>
    </div>
  </div>
</template>
