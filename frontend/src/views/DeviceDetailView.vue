<script setup lang="ts">
import { onMounted, computed, ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import { useDevicesStore } from "@/stores/devices"
import { useFavoritesStore } from "@/stores/favorites"
import { backupApi } from "@/api/backups"
import StatusBadge from "@/components/StatusBadge.vue"
import DiffViewer from "@/components/DiffViewer.vue"
import BackupContributionGraph from "@/components/BackupContributionGraph.vue"
import LoadingSpinner from "@/components/LoadingSpinner.vue"

interface BackupEntry {
  hash: string
  short_hash: string
  message: string
  author: string
  date: string
  timestamp: string
  file_size_bytes: number
  version_number: number
}

const route = useRoute()
const router = useRouter()
const devicesStore = useDevicesStore()
const favoritesStore = useFavoritesStore()

const deviceName = computed(() => route.params.name as string)
const isFavorite = computed(() => favoritesStore.isFavorite(deviceName.value))
const vendorName = computed(() => 
  devicesStore.selectedDevice ? devicesStore.getVendorName(devicesStore.selectedDevice.vendor) : ""
)

const backupHistory = ref<BackupEntry[]>([])
const historyLoading = ref(false)
const historyError = ref<string | null>(null)

// Filter states
const filterDateFrom = ref<string>("")
const filterDateTo = ref<string>("")
const filterSearch = ref<string>("")
const selectedDateInGraph = ref<string | null>(null)

// Pagination states
const currentPage = ref<number>(1)
const pageSize = ref<number>(10)

const selectedFromCommit = ref<string>("")
const selectedToCommit = ref<string>("")
const diffContent = ref<string>("")
const diffStats = ref({ added: 0, removed: 0 })
const diffLoading = ref(false)
const diffError = ref<string | null>(null)

onMounted(async () => {
  await devicesStore.fetchDevice(deviceName.value)
  if (devicesStore.vendors.length === 0) {
    await devicesStore.fetchVendors()
  }
  await loadBackupHistory()
})

async function loadBackupHistory() {
  historyLoading.value = true
  historyError.value = null

  try {
    const response = await backupApi.getHistory(deviceName.value)
    backupHistory.value = response.history || []

    // Auto-select the two most recent valid commits for diff
    if (commitOptions.value.length >= 2) {
      selectedFromCommit.value = commitOptions.value[1].hash
      selectedToCommit.value = commitOptions.value[0].hash
      await loadDiff()
    } else {
      selectedFromCommit.value = ""
      selectedToCommit.value = ""
      diffContent.value = ""
      diffStats.value = { added: 0, removed: 0 }
    }
  } catch (e) {
    historyError.value = e instanceof Error ? e.message : "Failed to load backup history"
  } finally {
    historyLoading.value = false
  }
}

// Filter computed property
const filteredBackupHistory = computed((): BackupEntry[] => {
  let filtered = backupHistory.value

  // Apply date range filters
  if (filterDateFrom.value) {
    const fromDate = new Date(filterDateFrom.value)
    filtered = filtered.filter(b => new Date(b.timestamp) >= fromDate)
  }

  if (filterDateTo.value) {
    const toDate = new Date(filterDateTo.value)
    toDate.setHours(23, 59, 59, 999) // Include entire day
    filtered = filtered.filter(b => new Date(b.timestamp) <= toDate)
  }

  // Apply date filter from graph selection
  if (selectedDateInGraph.value) {
    const selectedDay = new Date(selectedDateInGraph.value).toDateString()
    filtered = filtered.filter(b => new Date(b.timestamp).toDateString() === selectedDay)
  }

  // Apply search filter
  if (filterSearch.value) {
    const search = filterSearch.value.toLowerCase()
    filtered = filtered.filter(b => b.message.toLowerCase().includes(search))
  }

  return filtered
})

const hasActiveFilters = computed(
  () => filterDateFrom.value || filterDateTo.value || filterSearch.value || selectedDateInGraph.value
)

const commitOptions = computed((): BackupEntry[] => {
  return backupHistory.value.filter((backup) => backup.hash.trim() !== "" && backup.short_hash.trim() !== "")
})

// Pagination computed properties
const totalPages = computed(() => Math.ceil(filteredBackupHistory.value.length / pageSize.value))

const paginatedBackupHistory = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredBackupHistory.value.slice(start, end)
})

function clearFilters() {
  filterDateFrom.value = ""
  filterDateTo.value = ""
  filterSearch.value = ""
  selectedDateInGraph.value = null
  currentPage.value = 1 // Reset to first page when filters change
}

function setSelectedGraphDate(date: string) {
  selectedDateInGraph.value = date
}

function clearSelectedGraphDate() {
  selectedDateInGraph.value = null
}

function handlePageSizeChange() {
  currentPage.value = 1 // Reset to first page when page size changes
}

async function loadDiff() {
  if (!selectedFromCommit.value || !selectedToCommit.value) return

  diffLoading.value = true
  diffError.value = null

  try {
    const response = await backupApi.getDiff(
      deviceName.value,
      selectedFromCommit.value,
      selectedToCommit.value
    )
    diffContent.value = response.diff || ""
    diffStats.value = {
      added: response.lines_added || 0,
      removed: response.lines_removed || 0,
    }
  } catch (e) {
    diffError.value = e instanceof Error ? e.message : "Failed to load diff"
  } finally {
    diffLoading.value = false
  }
}

function goBack() {
  router.push("/devices")
}

async function toggleFavorite() {
  try {
    await favoritesStore.toggleFavorite(deviceName.value)
  } catch (e) {
    console.error("Failed to toggle favorite:", e)
  }
}

async function triggerBackup() {
  try {
    // Update device status to in_progress
    if (devicesStore.selectedDevice) {
      devicesStore.selectedDevice.status = "backup_in_progress"
      // Also update in the devices array
      const deviceIndex = devicesStore.devices.findIndex((d: { device_name: string }) => d.device_name === deviceName.value)
      if (deviceIndex >= 0) {
        devicesStore.devices[deviceIndex].status = "backup_in_progress"
      }
    }

    console.log("[Backup] Triggering backup for device:", deviceName.value)
    const response = await backupApi.triggerDevice(deviceName.value)
    console.log("[Backup] Trigger response:", response)
    alert(`Backup triggered: ${response.message}`)


    // Reload history after backup (for UI update)
    await loadBackupHistory()

    // Reload device data from API to get updated status from database
    await devicesStore.fetchDevice(deviceName.value)

    console.log("[Backup] Final status after reload:", devicesStore.selectedDevice?.status)
  } catch (e) {
    console.error("[Backup] Error during backup:", e)
    // Update device status to failed on error
    if (devicesStore.selectedDevice) {
      devicesStore.selectedDevice.status = "backup_failed"
      // Also update in the devices array
      const deviceIndex = devicesStore.devices.findIndex((d: { device_name: string }) => d.device_name === deviceName.value)
      if (deviceIndex >= 0) {
        devicesStore.devices[deviceIndex].status = "backup_failed"
      }
    }
    alert(`Backup failed: ${e instanceof Error ? e.message : "Unknown error"}`)
  }
}

// Download config file
async function downloadConfig(backup: BackupEntry) {
  try {
    const response = await backupApi.latestConfig(deviceName.value, backup.hash)
    const config = response.config || ""

    // Create blob and download
    const blob = new Blob([config], { type: "text/plain" })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = `${deviceName.value}-v${backup.version_number}.conf`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
  } catch (e) {
    alert(`Download failed: ${e instanceof Error ? e.message : "Unknown error"}`)
  }
}

// Format file size for display
function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 B"
  const k = 1024
  const sizes = ["B", "KB", "MB", "GB"]
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + " " + sizes[i]
}
</script>

<template>
  <div>
    <!-- Back Button -->
    <button @click="goBack" class="flex items-center text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 mb-6">
      <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-1" viewBox="0 0 20 20" fill="currentColor">
        <path fill-rule="evenodd" d="M9.707 16.707a1 1 0 01-1.414 0l-6-6a1 1 0 010-1.414l6-6a1 1 0 011.414 1.414L5.414 9H17a1 1 0 110 2H5.414l4.293 4.293a1 1 0 010 1.414z" clip-rule="evenodd" />
      </svg>
      Back to Devices
    </button>

    <LoadingSpinner v-if="devicesStore.loading" size="lg" class="py-12" />

    <div v-else-if="devicesStore.error" class="card text-center py-8">
      <p class="text-red-600">{{ devicesStore.error }}</p>
      <button @click="devicesStore.fetchDevice(deviceName)" class="btn btn-primary mt-4">
        Retry
      </button>
    </div>

    <div v-else-if="devicesStore.selectedDevice">
      <!-- Device header -->
      <div class="card mb-6">
        <div class="flex flex-col md:flex-row md:items-start md:justify-between">
          <div>
            <div class="flex items-center space-x-3">
              <h1 class="text-2xl font-bold text-gray-900 dark:text-gray-100">
                {{ devicesStore.selectedDevice.device_name }}
              </h1>
              <StatusBadge :status="devicesStore.selectedDevice.status" />
            </div>
            <p class="text-gray-500 dark:text-gray-400 font-mono mt-1">{{ devicesStore.selectedDevice.ip_address }}</p>
          </div>

          <!-- Favorite Button-->
          <div class="mt-4 md:mt-0 flex items-center gap-2">
            <button
              @click="toggleFavorite"
              class="px-3 py-2 rounded-md text-sm font-medium transition border"
              :class="isFavorite ? 'bg-amber-100 text-amber-700 border-amber-200 hover:bg-amber-200 dark:bg-amber-900/40 dark:text-amber-300 dark:border-amber-700 dark:hover:bg-amber-900/60' : 'bg-gray-100 text-gray-600 border-gray-200 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:border-gray-600 dark:hover:bg-gray-600'"
            >
              {{ isFavorite ? "★ Favorited" : "☆ Favorite" }}
            </button>
            <button @click="triggerBackup" class="btn btn-primary">
              Trigger Backup
            </button>
          </div>
        </div>

        <!-- Device details -->
        <div class="mt-6 grid grid-cols-2 md:grid-cols-5 gap-4">
          <div>
            <dt class="text-sm text-gray-500 dark:text-gray-400">Group</dt>
            <dd class="font-medium text-gray-900 dark:text-gray-100">{{ devicesStore.selectedDevice.group }}</dd>
          </div>
          <div>
            <dt class="text-sm text-gray-500 dark:text-gray-400">Vendor</dt>
            <dd class="font-medium text-gray-900 dark:text-gray-100">{{ vendorName }}</dd>
          </div>
          <div>
            <dt class="text-sm text-gray-500 dark:text-gray-400">SSH Profile</dt>
            <dd class="font-medium text-gray-900 dark:text-gray-100">{{ devicesStore.selectedDevice.ssh_profile }}</dd>
          </div>
          <div>
            <dt class="text-sm text-gray-500 dark:text-gray-400">Enabled</dt>
            <dd class="font-medium text-gray-900 dark:text-gray-100">{{ devicesStore.selectedDevice.enabled ? "Yes" : "No" }}</dd>
          </div>
          <div>
            <dt class="text-sm text-gray-500 dark:text-gray-400">Schedule</dt>
            <dd class="font-medium text-gray-900 dark:text-gray-100">{{ devicesStore.selectedDevice?.schedule || "No schedule" }}</dd>
          </div>
        </div>
      </div>

      <BackupContributionGraph
        :backups="backupHistory"
        :selected-date="selectedDateInGraph"
        @day-selected="setSelectedGraphDate"
        @day-cleared="clearSelectedGraphDate"
        class="mb-6"
      />

      <!-- Backup history section -->
      <div class="card mb-6">
        <h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Backup History</h2>

        <LoadingSpinner v-if="historyLoading" size="md" />

        <div v-else-if="historyError" class="text-red-600 text-sm mb-4">
          {{ historyError }}
        </div>

        <div v-else>
          <!-- Filter controls -->
          <div v-if="backupHistory.length > 0" class="p-4 mb-4 rounded-lg border border-gray-200/80 dark:border-slate-700/80 bg-white/70 dark:bg-slate-900/55 backdrop-blur-sm">
            <div class="space-y-3">
              <div class="flex flex-col md:flex-row gap-4">
                <div class="flex-1">
                  <label class="label">From Date</label>
                  <input v-model="filterDateFrom" type="date" class="input" />
                </div>
                <div class="flex-1">
                  <label class="label">To Date</label>
                  <input v-model="filterDateTo" type="date" class="input" />
                </div>
              </div>

              <div>
                <label class="label">Search Commit Message</label>
                <input
                  v-model="filterSearch"
                  type="text"
                  placeholder="Search backups..."
                  class="input"
                />
              </div>

              <div v-if="hasActiveFilters" class="flex items-center justify-between">
                <span class="text-sm text-gray-600 dark:text-gray-400">{{ filteredBackupHistory.length }} of {{ backupHistory.length }} backups</span>
                <button @click="clearFilters" class="text-sm text-kiwissh-600 dark:text-kiwissh-400 hover:text-kiwissh-700 dark:hover:text-kiwissh-300 underline">
                  Clear Filters
                </button>
              </div>

              <div class="flex items-center gap-4">
                <label class="label mb-0">Entries per page:</label>
                <select v-model.number="pageSize" @change="handlePageSizeChange" class="input w-24">
                  <option :value="5">5</option>
                  <option :value="10">10</option>
                  <option :value="20">20</option>
                  <option :value="50">50</option>
                </select>
              </div>
            </div>
          </div>

          <!-- Backup history list -->
          <div v-if="filteredBackupHistory.length === 0" class="text-center text-gray-500 dark:text-gray-400 py-8">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              class="h-12 w-12 mx-auto mb-4 text-gray-300 dark:text-gray-600"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <p>No backup history available</p>
            <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
              <span v-if="hasActiveFilters">No backups match your filters. </span>Click "Trigger Backup" to create the first backup
            </p>
          </div>

          <div v-else class="space-y-2 border border-gray-200 dark:border-gray-700 rounded-lg divide-y dark:divide-gray-700">
            <div
              v-for="backup in paginatedBackupHistory"
              :key="backup.hash"
              class="p-3 hover:bg-gray-50 dark:hover:bg-gray-800/70 transition-colors"
            >
              <div class="flex items-center justify-between gap-4">
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2 mb-1">
                    <span class="text-xs font-bold px-2 py-1 rounded-full bg-kiwissh-100 text-kiwissh-700 dark:bg-kiwissh-900/40 dark:text-kiwissh-300">
                      v{{ backup.version_number }}
                    </span>
                    <code class="text-sm font-mono bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-2 py-1 rounded">{{ backup.short_hash }}</code>
                    <span class="text-xs text-gray-500 dark:text-gray-400">{{ formatFileSize(backup.file_size_bytes) }}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-sm text-gray-700 dark:text-gray-200 font-medium truncate">{{ backup.message }}</span>
                  </div>
                  <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    {{ backup.author }} on {{ new Date(backup.timestamp).toLocaleString() }}
                  </p>
                </div>
                <button
                  @click="downloadConfig(backup)"
                  class="flex-shrink-0 btn btn-secondary py-1 px-3 text-sm whitespace-nowrap"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    class="h-4 w-4 inline mr-1"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      stroke-width="2"
                      d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                    />
                  </svg>
                  Download
                </button>
              </div>
            </div>
          </div>

          <!-- Pagination controls -->
          <div v-if="filteredBackupHistory.length > 0" class="mt-4 flex items-center justify-between">
            <span class="text-sm text-gray-600 dark:text-gray-400">
              Page {{ currentPage }} of {{ totalPages }} ({{ filteredBackupHistory.length }} total)
            </span>
            <div class="flex gap-2">
              <button
                @click="currentPage = Math.max(1, currentPage - 1)"
                :disabled="currentPage === 1"
                class="btn btn-secondary py-1 px-3 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                ← Previous
              </button>
              <button
                @click="currentPage = Math.min(totalPages, currentPage + 1)"
                :disabled="currentPage === totalPages"
                class="btn btn-secondary py-1 px-3 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Next →
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Config diff selector and viewer -->
      <div class="card mb-6">
        <h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Configuration Diff</h2>

        <div v-if="commitOptions.length >= 2" class="mb-4 flex flex-col md:flex-row gap-4">
          <div class="flex-1">
            <label class="label">From Commit</label>
            <select v-model="selectedFromCommit" @change="loadDiff" class="input">
              <option disabled value="">Select commit</option>
              <option v-for="backup in commitOptions" :key="`from-${backup.hash}`" :value="backup.hash">
                v{{ backup.version_number }} - {{ backup.short_hash }} - {{ backup.message.substring(0, 40) }}
              </option>
            </select>
          </div>
          <div class="flex-1">
            <label class="label">To Commit</label>
            <select v-model="selectedToCommit" @change="loadDiff" class="input">
              <option disabled value="">Select commit</option>
              <option v-for="backup in commitOptions" :key="`to-${backup.hash}`" :value="backup.hash">
                v{{ backup.version_number }} - {{ backup.short_hash }} - {{ backup.message.substring(0, 40) }}
              </option>
            </select>
          </div>
        </div>

        <LoadingSpinner v-if="diffLoading" size="md" />

        <div v-else-if="diffError" class="text-red-600 text-sm">
          {{ diffError }}
        </div>

        <DiffViewer
          v-else
          :diff-content="diffContent"
          :lines-added="diffStats.added"
          :lines-removed="diffStats.removed"
        />
      </div>
    </div>

    <div v-else class="card text-center py-12">
      <p class="text-gray-500 dark:text-gray-400">Device not found</p>
    </div>
  </div>
</template>
