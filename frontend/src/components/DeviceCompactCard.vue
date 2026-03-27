<script setup lang="ts">
import StatusBadge from "./StatusBadge.vue"
import type { Device } from "@/types/device"

defineProps<{
  device: Device
}>()
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
      <StatusBadge :status="device.status" />
    </div>
  </div>
</template>
