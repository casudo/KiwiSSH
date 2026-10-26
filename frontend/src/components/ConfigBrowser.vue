<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue"
import { backupApi } from "@/api/backups"
import type { BackupHistoryEntry } from "@/types/backup"
import LoadingSpinner from "@/components/LoadingSpinner.vue"

interface Props {
  deviceName: string
  versions: BackupHistoryEntry[]
  commit: string
}

interface LoadedVersion {
  commit: string
  versionNumber: number | null
  timestamp: string | null
  message: string
}

interface ContentSegment {
  text: string
  matchIndex: number | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  "update:commit": [commit: string]
}>()

// Cap highlighted matches so short search terms don't flood the DOM with <mark> elements
const MAX_HIGHLIGHTS = 1000

const config = ref<string | null>(null)
const loadedVersion = ref<LoadedVersion | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const searchQuery = ref("")
const activeMatchIndex = ref(0)
const copyStatus = ref<"idle" | "copied" | "failed">("idle")
const scrollContainer = ref<HTMLElement | null>(null)

let latestRequestId = 0
let copyResetTimer: ReturnType<typeof setTimeout> | undefined

const selectedCommit = computed({
  get: () => props.commit,
  set: (value: string) => emit("update:commit", value),
})

// Keep the viewed version selectable after the history list was paged away from it
const orphanedVersion = computed((): LoadedVersion | null => {
  const loaded = loadedVersion.value
  if (!loaded || loaded.commit !== props.commit) return null
  return props.versions.some((version) => version.hash === loaded.commit) ? null : loaded
})

// Normalize line endings and drop the final newline so it doesn't show up as an extra empty line
const content = computed(() => (config.value ?? "").replace(/\r\n?/g, "\n").replace(/\n$/, ""))
const lineCount = computed(() => (content.value ? content.value.split("\n").length : 0))
const lineNumbers = computed(() => Array.from({ length: lineCount.value }, (_, index) => index + 1).join("\n"))
const sizeBytes = computed(() => new Blob([config.value ?? ""]).size)

const hasQuery = computed(() => searchQuery.value.trim() !== "")

const search = computed((): { segments: ContentSegment[]; total: number } => {
  const text = content.value
  if (!text || !hasQuery.value) {
    return { segments: [{ text, matchIndex: null }], total: 0 }
  }

  const pattern = new RegExp(escapeRegExp(searchQuery.value), "gi")
  const segments: ContentSegment[] = []
  let total = 0
  let cursor = 0

  for (const match of text.matchAll(pattern)) {
    if (total < MAX_HIGHLIGHTS) {
      const start = match.index ?? 0
      if (start > cursor) {
        segments.push({ text: text.slice(cursor, start), matchIndex: null })
      }
      segments.push({ text: match[0], matchIndex: total })
      cursor = start + match[0].length
    }
    total += 1
  }

  if (cursor < text.length) {
    segments.push({ text: text.slice(cursor), matchIndex: null })
  }

  return { segments, total }
})

const highlightedCount = computed(() => Math.min(search.value.total, MAX_HIGHLIGHTS))

const matchLabel = computed(() => {
  if (!search.value.total) return "No matches"
  const suffix = search.value.total > MAX_HIGHLIGHTS ? "+" : ""
  return `${activeMatchIndex.value + 1} / ${highlightedCount.value}${suffix}`
})

const copyLabel = computed(() => {
  if (copyStatus.value === "copied") return "Copied!"
  if (copyStatus.value === "failed") return "Copy failed"
  return "Copy"
})

watch(
  () => [props.deviceName, props.commit] as const,
  () => void loadConfig(),
  { immediate: true },
)

watch(searchQuery, () => {
  activeMatchIndex.value = 0
  void nextTick(scrollToActiveMatch)
})

onBeforeUnmount(() => clearTimeout(copyResetTimer))

async function loadConfig() {
  const requestId = ++latestRequestId
  const commit = props.commit

  if (!commit) {
    config.value = null
    loadedVersion.value = null
    error.value = null
    loading.value = false
    return
  }

  loading.value = true
  error.value = null

  try {
    const response = await backupApi.latestConfig(props.deviceName, commit)
    // Ignore responses that arrive after the user already picked another version
    if (requestId !== latestRequestId) return

    config.value = response.config ?? ""
    loadedVersion.value = {
      commit,
      versionNumber: response.version_number ?? null,
      timestamp: response.timestamp,
      message: response.message,
    }
    activeMatchIndex.value = 0

    await nextTick()
    scrollContainer.value?.scrollTo(0, 0)
    scrollToActiveMatch()
  } catch (e) {
    if (requestId !== latestRequestId) return
    error.value = e instanceof Error ? e.message : "Failed to load configuration"
  } finally {
    if (requestId === latestRequestId) {
      loading.value = false
    }
  }
}

function goToMatch(index: number) {
  const count = highlightedCount.value
  if (!count) return
  activeMatchIndex.value = (index + count) % count
  void nextTick(scrollToActiveMatch)
}

// Scroll only the code pane so the page itself stays where it is
function scrollToActiveMatch() {
  const container = scrollContainer.value
  const mark = container?.querySelector<HTMLElement>(`[data-match="${activeMatchIndex.value}"]`)
  if (!container || !mark) return
  container.scrollTop = mark.offsetTop - container.clientHeight / 2
  container.scrollLeft = Math.max(0, mark.offsetLeft - container.clientWidth / 2)
}

function getMatchClass(matchIndex: number): string {
  return matchIndex === activeMatchIndex.value
    ? "bg-orange-300 text-gray-900 dark:bg-orange-500 dark:text-white rounded-sm"
    : "bg-amber-200 text-gray-900 dark:bg-amber-400/30 dark:text-amber-100 rounded-sm"
}

async function copyConfig() {
  const text = config.value ?? ""
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
    } else {
      copyWithTextarea(text)
    }
    setCopyStatus("copied")
  } catch {
    setCopyStatus("failed")
  }
}

// navigator.clipboard only exists on HTTPS/localhost, plain HTTP deployments need the legacy fallback
function copyWithTextarea(text: string) {
  const textarea = document.createElement("textarea")
  textarea.value = text
  textarea.setAttribute("readonly", "")
  textarea.style.position = "fixed"
  textarea.style.opacity = "0"
  document.body.appendChild(textarea)
  textarea.select()
  const copied = document.execCommand("copy")
  document.body.removeChild(textarea)
  if (!copied) {
    throw new Error("Copy command was rejected")
  }
}

function setCopyStatus(status: "copied" | "failed") {
  copyStatus.value = status
  clearTimeout(copyResetTimer)
  copyResetTimer = setTimeout(() => {
    copyStatus.value = "idle"
  }, 2000)
}

function downloadConfig() {
  const version = loadedVersion.value
  if (config.value === null || !version) return

  const versionLabel = version.versionNumber ? `v${version.versionNumber}` : version.commit.slice(0, 7)
  const blob = new Blob([config.value], { type: "text/plain" })
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = `${props.deviceName}-${versionLabel}.conf`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 B"
  const k = 1024
  const sizes = ["B", "KB", "MB", "GB"]
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + " " + sizes[i]
}
</script>

<template>
  <div v-if="!commit" class="text-center text-gray-500 dark:text-gray-400 py-8">
    <p>No configuration available</p>
    <p class="text-sm mt-1 text-gray-500 dark:text-gray-500">Trigger a backup to browse the device configuration</p>
  </div>

  <div v-else class="space-y-4">
    <!-- Version selector and search -->
    <div class="flex flex-col md:flex-row gap-4">
      <div class="flex-1">
        <label class="label" for="config-browser-version">Version</label>
        <select id="config-browser-version" v-model="selectedCommit" class="input">
          <option v-if="orphanedVersion" :value="orphanedVersion.commit">
            v{{ orphanedVersion.versionNumber }} - {{ orphanedVersion.commit.slice(0, 7) }} - {{ orphanedVersion.message.substring(0, 40) }}
          </option>
          <option v-for="backup in versions" :key="backup.hash" :value="backup.hash">
            v{{ backup.version_number }} - {{ backup.short_hash }} - {{ backup.message.substring(0, 40) }}
          </option>
        </select>
      </div>
      <div class="flex-1">
        <label class="label" for="config-browser-search">Search in File</label>
        <div class="flex gap-2">
          <div class="relative flex-1">
            <input
              id="config-browser-search"
              v-model="searchQuery"
              type="text"
              placeholder="Search configuration..."
              class="input pr-28"
              @keydown.enter.exact.prevent="goToMatch(activeMatchIndex + 1)"
              @keydown.enter.shift.prevent="goToMatch(activeMatchIndex - 1)"
              @keydown.esc="searchQuery = ''"
            />
            <span
              v-if="hasQuery"
              class="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-500 dark:text-gray-400 pointer-events-none"
              :title="search.total > MAX_HIGHLIGHTS ? `${search.total} matches, only the first ${MAX_HIGHLIGHTS} are highlighted` : undefined"
            >
              {{ matchLabel }}
            </span>
          </div>
          <button
            @click="goToMatch(activeMatchIndex - 1)"
            :disabled="!highlightedCount"
            class="btn btn-secondary px-3 disabled:opacity-50 disabled:cursor-not-allowed"
            title="Previous match (Shift+Enter)"
          >
            ↑
          </button>
          <button
            @click="goToMatch(activeMatchIndex + 1)"
            :disabled="!highlightedCount"
            class="btn btn-secondary px-3 disabled:opacity-50 disabled:cursor-not-allowed"
            title="Next match (Enter)"
          >
            ↓
          </button>
        </div>
      </div>
    </div>

    <div v-if="error" class="text-red-600 text-sm">
      {{ error }}
      <button @click="loadConfig" class="ml-2 underline hover:text-red-700">Retry</button>
    </div>

    <LoadingSpinner v-else-if="!loadedVersion" size="md" />

    <!-- File view -->
    <div v-else class="border border-slate-200 dark:border-slate-700 rounded-lg overflow-hidden">
      <div class="flex flex-wrap items-center justify-between gap-3 px-4 py-2 bg-slate-100/90 dark:bg-slate-800/95 border-b border-slate-200 dark:border-slate-700">
        <div class="flex flex-wrap items-center gap-x-3 gap-y-1 min-w-0 text-xs text-slate-600 dark:text-slate-300">
          <span class="flex items-center gap-1.5 font-mono text-sm font-medium text-slate-800 dark:text-slate-100">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            {{ deviceName }}.conf
          </span>
          <span
            v-if="loadedVersion.versionNumber"
            class="font-bold px-2 py-0.5 rounded-full bg-kiwissh-100 text-kiwissh-700 dark:bg-kiwissh-900/40 dark:text-kiwissh-300"
          >
            v{{ loadedVersion.versionNumber }}
          </span>
          <code class="font-mono">{{ loadedVersion.commit.slice(0, 7) }}</code>
          <span v-if="loadedVersion.timestamp">{{ new Date(loadedVersion.timestamp).toLocaleString() }}</span>
          <span>{{ lineCount.toLocaleString() }} lines · {{ formatFileSize(sizeBytes) }}</span>
          <LoadingSpinner v-if="loading" size="sm" />
        </div>
        <div class="flex items-center gap-2">
          <button @click="copyConfig" class="btn btn-secondary py-1 px-3 text-sm">
            {{ copyLabel }}
          </button>
          <button @click="downloadConfig" class="btn btn-secondary py-1 px-3 text-sm">
            Download
          </button>
        </div>
      </div>

      <div v-if="!content" class="px-4 py-8 text-center text-sm text-gray-500 dark:text-gray-400">
        This backup is empty
      </div>

      <!-- Line numbers and content are two <pre> blocks sharing one line height, so large configs stay cheap to render -->
      <div
        v-else
        ref="scrollContainer"
        class="relative max-h-144 overflow-auto font-mono text-sm leading-6 bg-slate-50/50 dark:bg-slate-900 transition-opacity"
        :class="{ 'opacity-50': loading }"
      >
        <div class="flex min-w-max">
          <pre
            aria-hidden="true"
            class="sticky left-0 shrink-0 px-3 py-2 text-right text-xs leading-6 text-gray-500 dark:text-gray-400 bg-slate-100 dark:bg-slate-800 border-r border-slate-200 dark:border-slate-700 select-none"
          >{{ lineNumbers }}</pre>
          <pre class="flex-1 px-4 py-2 leading-6 text-gray-800 dark:text-gray-100"><template
            v-for="(segment, segmentIndex) in search.segments"
            :key="segmentIndex"
          ><mark
            v-if="segment.matchIndex !== null"
            :data-match="segment.matchIndex"
            :class="getMatchClass(segment.matchIndex)"
          >{{ segment.text }}</mark><template v-else>{{ segment.text }}</template></template></pre>
        </div>
      </div>
    </div>
  </div>
</template>
