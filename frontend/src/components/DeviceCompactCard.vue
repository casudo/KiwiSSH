<script setup lang="ts">
import { ref } from "vue"
import StatusBadge from "./StatusBadge.vue"
import { backupApi } from "@/api/backups"
import type { Device } from "@/types/device"

const props = defineProps<{
  device: Device
}>()

const triggering = ref(false)

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
