<script setup lang="ts">
import { computed } from "vue"
import type { DeviceStatus } from "@/types/device"

interface StatusConfig {
  label: string
  class: string
}

const props = defineProps<{
  status: DeviceStatus
}>()

const statusConfigMap: Record<DeviceStatus, StatusConfig> = {
  unknown: { label: "Unknown", class: "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200" },
  backup_success: { label: "Backup Success", class: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300" },
  backup_failed: { label: "Backup Failed", class: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300" },
  backup_in_progress: { label: "Backup in Progress", class: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300" },
  backup_no_changes: { label: "No Changes", class: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300" },
}

const config = computed((): StatusConfig => {
  return statusConfigMap[props.status] || statusConfigMap.unknown
})
</script>

<template>
  <span
    class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
    :class="config.class"
  >
    {{ config.label }}
  </span>
</template>
