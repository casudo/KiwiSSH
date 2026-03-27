<script setup lang="ts">
import StatusBadge from "./StatusBadge.vue"
import type { Device } from "@/types/device"

defineProps<{
  device: Device
}>()
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
      <StatusBadge :status="device.status" />
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
