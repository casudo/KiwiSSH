import { defineStore } from "pinia"
import { ref, computed } from "vue"
import { deviceApi } from "@/api/devices"
import type { Device } from "@/types/device"

export const useDevicesStore = defineStore("devices", () => {
  // State
  const devices = ref<Device[]>([])
  const groups = ref<string[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const selectedDevice = ref<Device | null>(null)
  const isLoaded = ref(false) // Track if devices have been loaded

  // Getters
  const deviceCount = computed(() => devices.value.length)

  const enabledDevices = computed(() =>
    devices.value.filter(d => d.enabled)
  )

  const disabledDevices = computed(() =>
    devices.value.filter(d => !d.enabled)
  )

  const devicesByGroup = computed(() => {
    const grouped: Record<string, Device[]> = {}
    devices.value.forEach(device => {
      if (!grouped[device.group]) {
        grouped[device.group] = []
      }
      grouped[device.group].push(device)
    })
    return grouped
  })

  const devicesByStatus = computed(() => {
    const byStatus: Record<string, Device[]> = {}
    devices.value.forEach(device => {
      if (!byStatus[device.status]) {
        byStatus[device.status] = []
      }
      byStatus[device.status].push(device)
    })
    return byStatus
  })

  const uniqueVendors = computed(() => {
    return Array.from(new Set(devices.value.map(d => d.vendor))).sort()
  })

  const uniqueSshProfiles = computed(() => {
    return Array.from(new Set(devices.value.map(d => d.ssh_profile))).sort()
  })

  const devicesByVendor = computed(() => {
    const byVendor: Record<string, Device[]> = {}
    devices.value.forEach(device => {
      if (!byVendor[device.vendor]) {
        byVendor[device.vendor] = []
      }
      byVendor[device.vendor].push(device)
    })
    return byVendor
  })

  // Actions
  async function fetchDevices(params: Record<string, string> = {}, forceRefresh = false) {
    // Return cached devices if already loaded and not forcing refresh
    if (isLoaded.value && !forceRefresh && devices.value.length > 0) {
      console.log("[DevicesStore] Using cached devices:", devices.value.length)
      return
    }

    console.log("[DevicesStore] Fetching devices...", { forceRefresh, isLoaded: isLoaded.value })
    loading.value = true
    error.value = null

    try {
      devices.value = await deviceApi.getAll(params)
      isLoaded.value = true
      console.log("[DevicesStore] Devices fetched successfully:", devices.value.length)
    } catch (e: unknown) {
      const errMsg = e instanceof Error ? e.message : "Failed to fetch devices"
      error.value = errMsg
      console.error("[DevicesStore] Error fetching devices:", errMsg)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchGroups() {
    try {
      const response = await deviceApi.getGroups()
      groups.value = response.groups || []
    } catch (e) {
      console.error("Failed to fetch groups:", e)
    }
  }

  async function fetchDevice(deviceName: string) {
    loading.value = true
    error.value = null

    try {
      const device = await deviceApi.getByName(deviceName)
      const status = await deviceApi.getStatus(deviceName)
      selectedDevice.value = { ...device, status: status.status }

      // Also update in the devices array to keep them in sync
      const deviceIndex = devices.value.findIndex(d => d.device_name === deviceName)
      if (deviceIndex >= 0) {
        devices.value[deviceIndex] = selectedDevice.value
      }
    } catch (e: unknown) {
      const errMsg = e instanceof Error ? e.message : "Failed to fetch device"
      error.value = errMsg
      throw e
    } finally {
      loading.value = false
    }
  }

  async function reloadDevices() {
    loading.value = true
    error.value = null

    try {
      await deviceApi.reload()
      await fetchDevices({}, true) // Force refresh bypasses cache
    } catch (e: unknown) {
      const errMsg = e instanceof Error ? e.message : "Failed to reload devices"
      error.value = errMsg
      throw e
    } finally {
      loading.value = false
    }
  }

  function clearError() {
    error.value = null
  }

  function clearSelectedDevice() {
    selectedDevice.value = null
  }

  return {
    // State
    devices,
    groups,
    loading,
    error,
    selectedDevice,
    isLoaded,
    // Getters
    deviceCount,
    enabledDevices,
    disabledDevices,
    devicesByGroup,
    devicesByStatus,
    uniqueVendors,
    uniqueSshProfiles,
    devicesByVendor,
    // Actions
    fetchDevices,
    fetchGroups,
    fetchDevice,
    reloadDevices,
    clearError,
    clearSelectedDevice,
  }
})
