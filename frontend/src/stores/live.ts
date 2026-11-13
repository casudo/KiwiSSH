import { defineStore } from "pinia"
import { ref } from "vue"
import { useDevicesStore } from "@/stores/devices"
import { useJobsStore } from "@/stores/jobs"
import type { BackupJobRecord, JobEventMessage } from "@/types/backup"

// Delay before each reconnect attempt, the last value repeats
const RECONNECT_DELAYS_MS = [1000, 2000, 5000, 10000, 30000]

/**
 * Called with the jobs that changed. An empty list means the changes are unknown
 * (e.g. after a reconnect), so everything shown should be reloaded.
 */
type JobsChangedListener = (jobs: BackupJobRecord[]) => void

/**
 * Live backup job updates over the WebSocket /api/v1/backups/events.
 * Device statuses and the queue depth in the stores are updated automatically,
 * views that show more (e.g. job counts) register with onJobsChanged().
 */
export const useLiveStore = defineStore("live", () => {
  const connected = ref(false)

  const listeners = new Set<JobsChangedListener>()
  let socket: WebSocket | null = null
  let reconnectAttempt = 0
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined
  let hasConnectedBefore = false

  function connect() {
    if (socket) return

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
    socket = new WebSocket(`${protocol}//${window.location.host}/api/v1/backups/events`)

    socket.onopen = () => {
      connected.value = true
      reconnectAttempt = 0
      // Changes made while disconnected were missed
      if (hasConnectedBefore) resync()
      hasConnectedBefore = true
    }

    socket.onmessage = (event: MessageEvent<string>) => {
      try {
        handleMessage(JSON.parse(event.data) as JobEventMessage)
      } catch (e) {
        console.error("[Live] Failed to handle message:", e)
      }
    }

    // onerror is always followed by onclose, so reconnecting is handled there
    socket.onclose = () => {
      connected.value = false
      socket = null
      scheduleReconnect()
    }
  }

  function scheduleReconnect() {
    if (reconnectTimer !== undefined) return
    const delay = RECONNECT_DELAYS_MS[Math.min(reconnectAttempt, RECONNECT_DELAYS_MS.length - 1)]
    reconnectAttempt += 1
    reconnectTimer = setTimeout(() => {
      reconnectTimer = undefined
      connect()
    }, delay)
  }

  function handleMessage(message: JobEventMessage) {
    const jobsStore = useJobsStore()
    jobsStore.queueDepth = message.queue_depth
    useDevicesStore().applyJobUpdates(message.jobs)
    notify(message.jobs)
  }

  function resync() {
    useDevicesStore().fetchDevices({}, true).catch((e) => console.error("[Live] Failed to reload devices:", e))
    notify([])
  }

  function notify(jobs: BackupJobRecord[]) {
    for (const listener of listeners) {
      try {
        listener(jobs)
      } catch (e) {
        console.error("[Live] Listener failed:", e)
      }
    }
  }

  /** Register a listener for job changes, returns a function that removes it again */
  function onJobsChanged(listener: JobsChangedListener): () => void {
    listeners.add(listener)
    return () => listeners.delete(listener)
  }

  return {
    connected,
    connect,
    onJobsChanged,
  }
})
