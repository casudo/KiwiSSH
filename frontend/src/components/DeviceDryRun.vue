<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue"
import axios from "axios"
import { backupApi } from "@/api/backups"
import type { DryRunResult } from "@/types/backup"
import LoadingSpinner from "@/components/LoadingSpinner.vue"

const props = defineProps<{
  deviceName: string
}>()

// How often the state of a running test is fetched
const STATUS_POLL_INTERVAL_MS = 1000

const showDialog = ref(false)
const running = ref(false)
const result = ref<DryRunResult | null>(null)
const error = ref<string | null>(null)
const showConfig = ref(false)
let unmounted = false

const passed = computed(() => result.value?.status === "success")

const configLineCount = computed(() => {
  const config = result.value?.config
  return config ? config.replace(/\r\n?/g, "\n").replace(/\n$/, "").split("\n").length : 0
})

// What a backup would do with the captured config
const comparison = computed((): { label: string; hint: string } => {
  if (result.value?.has_changes === true) {
    return { label: "Changed", hint: "A backup would save a new version" }
  }
  if (result.value?.has_changes === false) {
    return { label: "No changes", hint: "A backup would save no new version" }
  }
  return { label: "No backup yet", hint: "A backup would save the first version" }
})

onBeforeUnmount(() => {
  unmounted = true
})

async function runTest() {
  showDialog.value = true
  // A test is already running, so only bring its dialog back
  if (running.value) return

  running.value = true
  result.value = null
  error.value = null

  try {
    let dryRun = await backupApi.startDryRun(props.deviceName)
    while (dryRun.status === "in_progress") {
      await new Promise((resolve) => setTimeout(resolve, STATUS_POLL_INTERVAL_MS))
      if (unmounted) return
      dryRun = await backupApi.getDryRun(dryRun.dry_run_id)
    }

    result.value = dryRun
    // A failed test is explained best by what the device answered
    showConfig.value = dryRun.status === "failed"
  } catch (e) {
    error.value = getErrorMessage(e)
  } finally {
    running.value = false
    // Show the outcome even if the dialog was closed while the test was running
    showDialog.value = true
  }
}

// Prefer the reason given by the backend (e.g. a backup of the device is running) over "Request failed with status code 409"
function getErrorMessage(e: unknown): string {
  if (axios.isAxiosError(e) && typeof e.response?.data?.detail === "string") {
    return e.response.data.detail
  }
  return e instanceof Error ? e.message : "Unknown error"
}

function formatDuration(seconds?: number | null): string {
  if (seconds === null || seconds === undefined) return "N/A"
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
}

function formatFileSize(bytes?: number | null): string {
  if (bytes === null || bytes === undefined) return "N/A"
  if (bytes === 0) return "0 B"
  const k = 1024
  const sizes = ["B", "KB", "MB", "GB"]
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + " " + sizes[i]
}
</script>

<template>
  <button
    @click="runTest"
    class="btn btn-secondary"
    title="Test the connectivity and backup commands without saving a backup"
  >
    <svg
      v-if="running"
      xmlns="http://www.w3.org/2000/svg"
      class="h-4 w-4 inline mr-1 animate-spin"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle
        class="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        stroke-width="4"
      />
      <path
        class="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
    <svg
      v-else
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
        d="M5.636 18.364a9 9 0 010-12.728m12.728 0a9 9 0 010 12.728m-9.9-2.829a5 5 0 010-7.07m7.072 0a5 5 0 010 7.07M13 12a1 1 0 11-2 0 1 1 0 012 0z"
      />
    </svg>
    {{ running ? "Testing..." : "Test Device" }}
  </button>

  <!-- Teleported because the card around the button would otherwise confine the fixed overlay (backdrop-filter) -->
  <Teleport to="body">
    <div
      v-if="showDialog"
      @click="showDialog = false"
      class="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50"
    >
      <div
        @click.stop
        class="bg-white dark:bg-slate-800 rounded-lg shadow-xl dark:shadow-black/50 max-w-3xl w-full max-h-[85vh] flex flex-col"
      >
        <div class="border-b border-gray-200 dark:border-slate-700 px-6 py-4 flex items-center justify-between gap-4">
          <div class="min-w-0">
            <h2 class="text-xl font-semibold text-gray-900 dark:text-gray-100">Test Device</h2>
            <p class="text-sm font-mono text-gray-500 dark:text-gray-400 truncate">{{ deviceName }}</p>
          </div>
          <button
            @click="showDialog = false"
            class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div class="px-6 py-4 overflow-y-auto">
          <!-- Running -->
          <div v-if="running" class="flex items-center gap-4 py-6">
            <LoadingSpinner size="md" />
            <div>
              <p class="font-medium text-gray-900 dark:text-gray-100">Testing the device...</p>
              <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
                Connecting to the device and running its backup commands.
              </p>
            </div>
          </div>

          <!-- The test could not be started or followed -->
          <div v-else-if="error" class="p-4 bg-red-50 dark:bg-red-900/20 rounded text-red-700 dark:text-red-300">
            <p class="font-semibold">The test could not be run</p>
            <p class="text-sm mt-1 whitespace-pre-wrap wrap-break-word">{{ error }}</p>
          </div>

          <!-- Result -->
          <div v-else-if="result">
            <div
              class="p-4 rounded flex items-start gap-3"
              :class="passed
                ? 'bg-emerald-50 text-emerald-800 dark:bg-emerald-900/25 dark:text-emerald-300'
                : 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-300'"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                class="h-6 w-6 shrink-0"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  :d="passed
                    ? 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z'
                    : 'M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z'"
                />
              </svg>
              <div class="min-w-0">
                <p class="font-semibold">{{ passed ? "Test passed" : "Test failed" }}</p>
                <p class="text-sm mt-1 whitespace-pre-wrap wrap-break-word">
                  {{ passed
                    ? "The device was reached and its backup commands returned a valid configuration."
                    : result.error_message || "Unknown error" }}
                </p>
              </div>
            </div>

            <div class="grid grid-cols-2 gap-4 mt-4" :class="{ 'md:grid-cols-4': passed }">
              <div class="rounded border border-gray-200 dark:border-slate-700 p-3">
                <p class="text-sm text-gray-500 dark:text-gray-400 mb-1">Duration</p>
                <p class="font-medium text-gray-900 dark:text-gray-100">{{ formatDuration(result.duration_seconds) }}</p>
              </div>

              <template v-if="passed">
                <div class="rounded border border-gray-200 dark:border-slate-700 p-3">
                  <p class="text-sm text-gray-500 dark:text-gray-400 mb-1">Config Size</p>
                  <p class="font-medium text-gray-900 dark:text-gray-100">{{ formatFileSize(result.config_size_bytes) }}</p>
                </div>

                <div class="rounded border border-gray-200 dark:border-slate-700 p-3">
                  <p class="text-sm text-gray-500 dark:text-gray-400 mb-1">Lines</p>
                  <p class="font-medium text-gray-900 dark:text-gray-100">{{ configLineCount.toLocaleString() }}</p>
                </div>

                <div class="rounded border border-gray-200 dark:border-slate-700 p-3">
                  <p class="text-sm text-gray-500 dark:text-gray-400 mb-1">Latest Backup</p>
                  <p class="font-medium text-gray-900 dark:text-gray-100">{{ comparison.label }}</p>
                  <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">{{ comparison.hint }}</p>
                </div>
              </template>
            </div>

            <div v-if="result.metadata_output" class="mt-4">
              <p class="text-sm text-gray-500 dark:text-gray-400 mb-1">Metadata Output</p>
              <pre class="text-xs whitespace-pre-wrap wrap-break-word bg-gray-50 dark:bg-slate-900 border border-gray-200 dark:border-slate-700 rounded p-3 text-gray-800 dark:text-gray-200 max-h-48 overflow-auto">{{ result.metadata_output }}</pre>
            </div>

            <!-- Only rendered on demand, a config can be several MB -->
            <div v-if="result.config" class="mt-4">
              <button
                @click="showConfig = !showConfig"
                class="text-sm text-kiwissh-600 dark:text-kiwissh-400 hover:text-kiwissh-700 dark:hover:text-kiwissh-300 font-medium"
              >
                {{ showConfig ? "▼ Hide" : "▶ Show" }} Captured Configuration ({{ configLineCount.toLocaleString() }} lines)
              </button>
              <pre
                v-if="showConfig"
                class="mt-2 text-xs whitespace-pre-wrap wrap-break-word bg-gray-50 dark:bg-slate-900 border border-gray-200 dark:border-slate-700 rounded p-3 text-gray-800 dark:text-gray-200 max-h-72 overflow-auto"
              >{{ result.config }}</pre>
            </div>
          </div>
        </div>

        <div class="px-6 py-4 bg-gray-50 dark:bg-slate-900 border-t border-gray-200 dark:border-slate-700 rounded-b-lg flex items-center justify-between gap-4">
          <p class="text-xs text-gray-500 dark:text-gray-400">
            A dry run saves nothing: It's just for testing.
          </p>
          <div class="flex gap-2 shrink-0">
            <button v-if="!running" @click="runTest" class="btn btn-secondary">
              Run Again
            </button>
            <button @click="showDialog = false" class="btn btn-primary">
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
