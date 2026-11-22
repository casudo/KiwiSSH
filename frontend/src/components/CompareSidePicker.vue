<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { backupApi } from "@/api/backups"
import type { BackupHistoryEntry } from "@/types/backup"
import type { Device } from "@/types/device"
import DeviceCombobox from "@/components/DeviceCombobox.vue"

interface Props {
  label: string
  inputId: string
  devices: Device[]
}

const props = defineProps<Props>()

const device = defineModel<string>("device", { required: true })
const commit = defineModel<string>("commit", { required: true }) // Empty string means the latest backup

// Older versions can still be compared through a link, the list only offers the most recent ones
const VERSION_LIMIT = 50

const versions = ref<BackupHistoryEntry[]>([])
const versionsLoading = ref(false)
const versionsError = ref<string | null>(null)
let versionsRequestId = 0

const isKnownDevice = computed(() => props.devices.some((option) => option.device_name === device.value.trim()))
const showUnknownDevice = computed(() => device.value.trim() !== "" && props.devices.length > 0 && !isKnownDevice.value)
const hasNoBackups = computed(() => (
  isKnownDevice.value && !versionsLoading.value && !versionsError.value && versions.value.length === 0
))

// Keep a commit from a link selectable when it isn't among the listed versions
const commitNotListed = computed(() => (
  commit.value !== "" && !versions.value.some((version) => version.hash === commit.value)
))

// Only load once the input holds a known device, not on every keystroke
watch(
  () => (isKnownDevice.value ? device.value.trim() : ""),
  (deviceName) => void loadVersions(deviceName),
  { immediate: true },
)

async function loadVersions(deviceName: string) {
  const requestId = ++versionsRequestId
  versions.value = []
  versionsError.value = null

  if (!deviceName) {
    versionsLoading.value = false
    return
  }

  versionsLoading.value = true
  try {
    const response = await backupApi.getHistory(deviceName, VERSION_LIMIT)
    if (requestId !== versionsRequestId) return
    versions.value = response.history || []
  } catch (e) {
    if (requestId !== versionsRequestId) return
    versionsError.value = e instanceof Error ? e.message : "Failed to load versions"
  } finally {
    if (requestId === versionsRequestId) {
      versionsLoading.value = false
    }
  }
}

// A version picked for the previous device doesn't belong to the new one
function onDeviceChange(deviceName: string) {
  if (deviceName.trim() !== device.value.trim()) {
    commit.value = ""
  }
  device.value = deviceName
}

function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp)
  return Number.isNaN(date.getTime()) ? timestamp : date.toLocaleString()
}
</script>

<template>
  <div class="space-y-3">
    <div>
      <label class="label" :for="`${inputId}-device`">{{ label }}</label>
      <DeviceCombobox
        :input-id="`${inputId}-device`"
        :devices="devices"
        :model-value="device"
        @update:model-value="onDeviceChange"
      />
      <p v-if="showUnknownDevice" class="mt-1 text-xs text-red-600 dark:text-red-400">Unknown device</p>
    </div>

    <div>
      <label class="label" :for="`${inputId}-version`">Version</label>
      <select
        :id="`${inputId}-version`"
        v-model="commit"
        class="input"
        :disabled="!isKnownDevice || versionsLoading"
      >
        <option value="">Latest backup</option>
        <option v-if="commitNotListed" :value="commit">Commit {{ commit.slice(0, 7) }}</option>
        <option v-for="version in versions" :key="version.hash" :value="version.hash">
          v{{ version.version_number }} · {{ version.short_hash }} · {{ formatTimestamp(version.timestamp) }}
        </option>
      </select>
      <p v-if="versionsError" class="mt-1 text-xs text-red-600 dark:text-red-400">{{ versionsError }}</p>
      <p v-else-if="hasNoBackups" class="mt-1 text-xs text-amber-600 dark:text-amber-400">This device has no backups yet</p>
    </div>
  </div>
</template>
