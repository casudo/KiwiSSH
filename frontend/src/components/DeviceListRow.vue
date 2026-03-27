<script setup lang="ts">
import { ref } from "vue"
import StatusBadge from "./StatusBadge.vue"
import { backupApi } from "@/api/backups"
import type { Device } from "@/types/device"

const props = defineProps<{
  device?: Device
  isHeader?: boolean
}>()

const triggering = ref(false)

async function handleTriggerBackup(e: Event) {
  e.stopPropagation()

  if (triggering.value || !props.device) return
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
  <div :class="['border-b border-gray-200 last:border-b-0', isHeader ? 'bg-gray-50 sticky top-0' : 'hover:bg-gray-50']">
    <div class="grid grid-cols-2 md:grid-cols-7 gap-4 px-4 py-3 text-sm">
      <!-- Device Name -->
      <div :class="isHeader ? 'font-semibold text-gray-700' : 'font-medium text-gray-900'">
        {{ isHeader ? "Device Name" : device?.device_name }}
      </div>

      <!-- IP Address -->
      <div :class="['hidden md:block', isHeader ? 'font-semibold text-gray-700' : 'text-gray-600 font-mono text-xs']">
        {{ isHeader ? "IP Address" : device?.ip_address }}
      </div>

      <!-- Group -->
      <div :class="['hidden md:block', isHeader ? 'font-semibold text-gray-700' : 'text-gray-600']">
        {{ isHeader ? "Group" : device?.group }}
      </div>

      <!-- Vendor -->
      <div :class="['hidden lg:block', isHeader ? 'font-semibold text-gray-700' : 'text-gray-600']">
        {{ isHeader ? "Vendor" : device?.vendor }}
      </div>

      <!-- SSH Profile -->
      <div :class="['hidden lg:block', isHeader ? 'font-semibold text-gray-700' : 'text-gray-600']">
        {{ isHeader ? "SSH Profile" : device?.ssh_profile }}
      </div>

      <!-- Status -->
      <div :class="['hidden md:flex md:justify-center', isHeader ? 'font-semibold text-gray-700' : '']">
        {{ isHeader ? "Status" : '' }}
        <StatusBadge v-if="device" :status="device.status" />
      </div>

      <!-- Backup Button / Header -->
      <div class="flex justify-center">
        {{ isHeader ? "Backup" : '' }}
        <button
          v-if="!isHeader"
          @click="handleTriggerBackup"
          :disabled="triggering"
          class="px-2 py-1 text-xs bg-downtown-100 text-downtown-700 hover:bg-downtown-200 rounded transition"
          title="Trigger backup"
        >
          {{ triggering ? "..." : "▶" }}
        </button>
      </div>
    </div>
  </div>
</template>
