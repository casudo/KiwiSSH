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
  <div class="card-hover">
    <div class="flex items-start justify-between">
      <div class="flex-1 min-w-0">
        <h3 class="text-lg font-semibold text-gray-900 truncate">
          {{ device.device_name }}
        </h3>
        <p class="text-sm text-gray-500 font-mono">{{ device.ip_address }}</p>
      </div>
      <div class="flex items-center gap-2 flex-shrink-0">
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
