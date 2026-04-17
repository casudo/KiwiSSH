<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue"
import StatusBadge from "./StatusBadge.vue"
import { backupApi } from "@/api/backups"
import { useFavoritesStore } from "@/stores/favorites"
import type { Device } from "@/types/device"

const props = defineProps<{
  device?: Device
  isHeader?: boolean
}>()

type TriggerFeedbackState = "idle" | "loading" | "success" | "error"

const favoritesStore = useFavoritesStore()
const triggerFeedback = ref<TriggerFeedbackState>("idle")
let triggerFeedbackTimer: number | undefined
const isFavorite = computed(() => {
  if (!props.device) return false
  return favoritesStore.isFavorite(props.device.device_name)
})

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
  if (!props.device) return
  try {
    await favoritesStore.toggleFavorite(props.device.device_name)
  } catch (error) {
    console.error("Failed to toggle favorite:", error)
  }
}

async function handleTriggerBackup(e: Event) {
  e.stopPropagation()

  if (triggerFeedback.value === "loading" || !props.device) return

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
  <div :class="['border-b border-gray-200 dark:border-gray-700 last:border-b-0', isHeader ? 'bg-gray-50 dark:bg-gray-800 sticky top-0' : 'hover:bg-gray-50 dark:hover:bg-gray-800/70']">
    <div class="grid grid-cols-2 md:grid-cols-7 gap-4 px-4 py-3 text-sm">
      <!-- Device Name -->
      <div :class="isHeader ? 'font-semibold text-gray-700 dark:text-gray-300' : 'font-medium text-gray-900 dark:text-gray-100'">
        {{ isHeader ? "Device Name" : device?.device_name }}
      </div>

      <!-- IP Address -->
      <div :class="['hidden md:block', isHeader ? 'font-semibold text-gray-700 dark:text-gray-300' : 'text-gray-600 dark:text-gray-400 font-mono text-xs']">
        {{ isHeader ? "IP Address" : device?.ip_address }}
      </div>

      <!-- Group -->
      <div :class="['hidden md:block', isHeader ? 'font-semibold text-gray-700 dark:text-gray-300' : 'text-gray-600 dark:text-gray-400']">
        {{ isHeader ? "Group" : device?.group }}
      </div>

      <!-- Vendor -->
      <div :class="['hidden lg:block', isHeader ? 'font-semibold text-gray-700 dark:text-gray-300' : 'text-gray-600 dark:text-gray-400']">
        {{ isHeader ? "Vendor" : device?.vendor }}
      </div>

      <!-- SSH Profile -->
      <div :class="['hidden lg:block', isHeader ? 'font-semibold text-gray-700 dark:text-gray-300' : 'text-gray-600 dark:text-gray-400']">
        {{ isHeader ? "SSH Profile" : device?.ssh_profile }}
      </div>

      <!-- Status -->
      <div :class="['hidden md:flex md:justify-center', isHeader ? 'font-semibold text-gray-700 dark:text-gray-300' : '']">
        {{ isHeader ? "Status" : '' }}
        <StatusBadge v-if="device" :status="device.status" />
      </div>

      <!-- Actions -->
      <div class="flex justify-center">
        <span v-if="isHeader" class="font-semibold text-gray-700 dark:text-gray-300">Actions</span>
        <div v-else class="flex items-center gap-2">
          <!-- Favorite Button -->
          <button
            @click="handleToggleFavorite"
            class="px-2 py-1 text-xs rounded transition border"
            :class="isFavorite ? 'bg-amber-100 text-amber-700 border-amber-200 hover:bg-amber-200 dark:bg-amber-900/40 dark:text-amber-300 dark:border-amber-700 dark:hover:bg-amber-900/60' : 'bg-gray-100 text-gray-500 border-gray-200 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:border-gray-600 dark:hover:bg-gray-600'"
            :title="isFavorite ? 'Remove from favorites' : 'Add to favorites'"
            :aria-label="isFavorite ? 'Remove from favorites' : 'Add to favorites'"
          >
            {{ isFavorite ? "★" : "☆" }}
          </button>
          <!-- Trigger Backup Button -->
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
    </div>
  </div>
</template>
