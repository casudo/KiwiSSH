<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue"
import StatusBadge from "./StatusBadge.vue"
import { backupApi } from "@/api/backups"
import { useFavoritesStore } from "@/stores/favorites"
import type { Device } from "@/types/device"

const props = defineProps<{
  device: Device
}>()

type TriggerFeedbackState = "idle" | "loading" | "success" | "error"

const favoritesStore = useFavoritesStore()
const triggerFeedback = ref<TriggerFeedbackState>("idle")
const triggerFeedbackMessage = ref<string>("")
let triggerFeedbackTimer: number | undefined
let triggerFeedbackMessageTimer: number | undefined
const isFavorite = computed(() => favoritesStore.isFavorite(props.device.device_name))

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

function setTriggerFeedbackMessage(message: string, resetAfterMs: number = 0) {
  triggerFeedbackMessage.value = message

  if (triggerFeedbackMessageTimer !== undefined) {
    window.clearTimeout(triggerFeedbackMessageTimer)
    triggerFeedbackMessageTimer = undefined
  }

  if (resetAfterMs > 0) {
    triggerFeedbackMessageTimer = window.setTimeout(() => {
      triggerFeedbackMessage.value = ""
      triggerFeedbackMessageTimer = undefined
    }, resetAfterMs)
  }
}

onBeforeUnmount(() => {
  if (triggerFeedbackTimer !== undefined) {
    window.clearTimeout(triggerFeedbackTimer)
  }
  if (triggerFeedbackMessageTimer !== undefined) {
    window.clearTimeout(triggerFeedbackMessageTimer)
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
    const response = await backupApi.triggerDevice(props.device.device_name)
    setTriggerFeedback("success", 2500)
    setTriggerFeedbackMessage(`Backup triggered: ${response.message}`, 10000)
  } catch (error) {
    setTriggerFeedback("error", 4000)
    console.error("Failed to trigger backup:", error)
  }
}
</script>

<template>
  <div class="card-hover p-4">
    <div class="flex items-start justify-between gap-2">
      <div class="flex-1 min-w-0">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
          {{ device.device_name }}
        </h3>
        <p class="text-xs text-gray-500 dark:text-gray-400 font-mono truncate">{{ device.ip_address }}</p>
      </div>
      <div class="flex items-center gap-1 shrink-0">
        <button
          @click="handleToggleFavorite"
          class="px-1.5 py-0.5 text-xs rounded transition border"
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
          class="px-1.5 py-0.5 text-xs rounded transition"
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
    <p v-if="triggerFeedbackMessage" class="mt-2 text-xs text-gray-500 dark:text-gray-400">
      {{ triggerFeedbackMessage }}
    </p>
  </div>
</template>
