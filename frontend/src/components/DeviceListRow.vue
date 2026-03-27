<script setup lang="ts">
import StatusBadge from "./StatusBadge.vue"
import type { Device } from "@/types/device"

defineProps<{
  device: Device
}>()
</script>

<template>
  <div class="border-b border-gray-200 last:border-b-0">
    <div class="grid grid-cols-2 md:grid-cols-7 gap-4 px-4 py-3 text-sm">
      <!-- Device Name -->
      <div class="font-medium text-gray-900 truncate">
        {{ device.device_name }}
      </div>

      <!-- IP Address -->
      <div class="text-gray-600 font-mono text-xs hidden md:block truncate">
        {{ device.ip_address }}
      </div>

      <!-- Group -->
      <div class="text-gray-600 hidden md:block truncate">
        {{ device.group }}
      </div>

      <!-- Vendor -->
      <div class="text-gray-600 hidden lg:block truncate">
        {{ device.vendor }}
      </div>

      <!-- SSH Profile -->
      <div class="text-gray-600 hidden lg:block truncate">
        {{ device.ssh_profile }}
      </div>

      <!-- Status -->
      <div class="hidden md:flex md:justify-center">
        <StatusBadge :status="device.status" />
      </div>
    </div>
  </div>
</template>
