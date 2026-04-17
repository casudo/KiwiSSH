<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue"
import StatusBadge from "./StatusBadge.vue"
import { backupApi } from "@/api/backups"
import { useFavoritesStore } from "@/stores/favorites"
import { useDevicesStore } from "@/stores/devices"
import type { Device } from "@/types/device"

const props = defineProps<{
  device: Device
}>()

type TriggerFeedbackState = "idle" | "loading" | "success" | "error"

const favoritesStore = useFavoritesStore()
const devicesStore = useDevicesStore()
const triggerFeedback = ref<TriggerFeedbackState>("idle")
let triggerFeedbackTimer: number | undefined
const isFavorite = computed(() => favoritesStore.isFavorite(props.device.device_name))
const vendorName = computed(() => devicesStore.getVendorName(props.device.vendor))

function setTriggerFeedback(state: TriggerFeedbackState, resetAfterMs: number = 0) {
  triggerFeedback.value = state

  if (triggerFeedbackTimer !== undefined) {
    window.clearTimeout(triggerFeedbackTimer)
    triggerFeedbackTimer = undefined
  }

  if (resetAfterMs > 0) {
    triggerFeedbackTimer = window.setTimeout(() => {
      triggerFeedback.value = "idle"
      triggerFeedbackTimer = undefined
    }, resetAfterMs)
  }
}

onBeforeUnmount(() => {
  if (triggerFeedbackTimer !== undefined) {
    window.clearTimeout(triggerFeedbackTimer)
  }
})

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

  if (triggerFeedback.value === "loading") return

  setTriggerFeedback("loading")

  try {
    await backupApi.triggerDevice(props.device.device_name)
    setTriggerFeedback("success", 2500)
  } catch (error) {
    setTriggerFeedback("error", 4000)
    console.error("Failed to trigger backup:", error)
  }
}
</script>

<template>
  <div class="card-hover">
    <div class="flex items-start justify-between">
      <div class="flex-1 min-w-0">
        <h3 class="text-lg font-semibold text-gray-900 dark:text-gray-100 truncate">
          {{ device.device_name }}
        </h3>
        <p class="text-sm text-gray-500 dark:text-gray-400 font-mono">{{ device.ip_address }}</p>
      </div>
      <div class="flex items-center gap-2 shrink-0">
        <button
          @click="handleToggleFavorite"
          class="px-2 py-1 text-xs rounded transition border"
          :class="isFavorite ? 'bg-amber-100 text-amber-700 border-amber-200 hover:bg-amber-200 dark:bg-amber-900/40 dark:text-amber-300 dark:border-amber-700 dark:hover:bg-amber-900/60' : 'bg-gray-100 text-gray-500 border-gray-200 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:border-gray-600 dark:hover:bg-gray-600'"
          :title="isFavorite ? 'Remove from favorites' : 'Add to favorites'"
          :aria-label="isFavorite ? 'Remove from favorites' : 'Add to favorites'"
        >
          {{ isFavorite ? "★" : "☆" }}
        </button>
        <StatusBadge :status="device.status" />
        <button
          @click="handleTriggerBackup"
          :disabled="triggerFeedback === 'loading'"
          class="px-2 py-1 text-xs rounded transition"
          :class="
            triggerFeedback === 'success'
              ? 'bg-emerald-100 text-emerald-700 hover:bg-emerald-200 dark:bg-emerald-900/40 dark:text-emerald-300 dark:hover:bg-emerald-900/60'
              : triggerFeedback === 'error'
                ? 'bg-rose-100 text-rose-700 hover:bg-rose-200 dark:bg-rose-900/40 dark:text-rose-300 dark:hover:bg-rose-900/60'
                : 'bg-kiwissh-100 text-kiwissh-700 hover:bg-kiwissh-200 dark:bg-kiwissh-900/40 dark:text-kiwissh-300 dark:hover:bg-kiwissh-900/60'
          "
          :title="
            triggerFeedback === 'success'
              ? 'Backup queued'
              : triggerFeedback === 'error'
                ? 'Failed to queue backup'
                : 'Trigger backup'
          "
        >
          {{
            triggerFeedback === "loading"
              ? "..."
              : triggerFeedback === "success"
                ? "✓"
                : triggerFeedback === "error"
                  ? "!"
                  : "▶"
          }}
        </button>
      </div>
    </div>

    <div class="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-gray-600 dark:text-gray-300">
      <span class="flex items-center">
        <span class="text-gray-400 dark:text-gray-500 mr-1">Group:</span>
        <span class="font-medium">{{ device.group }}</span>
      </span>
      <span class="flex items-center">
        <span class="text-gray-400 dark:text-gray-500 mr-1">Vendor:</span>
        <span class="font-medium">{{ vendorName }}</span>
      </span>
    </div>

    <div class="mt-3 flex items-center justify-between">
      <div v-if="!device.enabled" class="text-xs text-amber-600 dark:text-amber-300 font-medium">
        Disabled
      </div>
      <div v-else-if="device.last_backup" class="text-xs text-gray-400 dark:text-gray-500">
        Last backup: {{ new Date(device.last_backup).toLocaleString() }}
      </div>
      <div v-else class="text-xs text-gray-400 dark:text-gray-500">
        No backups yet
      </div>
    </div>
  </div>
</template>
