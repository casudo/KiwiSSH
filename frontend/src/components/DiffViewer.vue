<script setup lang="ts">
import { computed, ref, watch } from "vue"

interface DiffSegment {
  text: string
  changed: boolean
}

interface DiffLine {
  type: "context" | "added" | "removed" | "header"
  content: string
  lineNum: number | null
  segments: DiffSegment[]
}

interface DiffRow {
  left: DiffLine | null
  right: DiffLine | null
}

interface Props {
  diffContent: string
  linesAdded: number
  linesRemoved: number
}

const props = defineProps<Props>()

const MAX_DIFF_LINES = 100
const showFullDiff = ref(false)

const diffLines = computed(() => (props.diffContent ? props.diffContent.split("\n") : []))
const diffLineCount = computed(() => diffLines.value.length)
const isLargeDiff = computed(() => diffLineCount.value > MAX_DIFF_LINES)
const visibleDiffLines = computed(() => (
  isLargeDiff.value && !showFullDiff.value
    ? diffLines.value.slice(0, MAX_DIFF_LINES)
    : diffLines.value
))

watch(
  () => props.diffContent,
  () => {
    showFullDiff.value = false
  },
)

function buildInlineSegments(
  removedText: string,
  addedText: string,
): { removedSegments: DiffSegment[]; addedSegments: DiffSegment[] } {
  const minLength = Math.min(removedText.length, addedText.length)

  let prefixLength = 0
  while (prefixLength < minLength && removedText[prefixLength] === addedText[prefixLength]) {
    prefixLength += 1
  }

  let suffixLength = 0
  while (
    removedText.length - suffixLength - 1 >= prefixLength
    && addedText.length - suffixLength - 1 >= prefixLength
    && removedText[removedText.length - suffixLength - 1] === addedText[addedText.length - suffixLength - 1]
  ) {
    suffixLength += 1
  }

  const removedPrefix = removedText.slice(0, prefixLength)
  const removedChanged = removedText.slice(prefixLength, removedText.length - suffixLength)
  const removedSuffix = removedText.slice(removedText.length - suffixLength)

  const addedPrefix = addedText.slice(0, prefixLength)
  const addedChanged = addedText.slice(prefixLength, addedText.length - suffixLength)
  const addedSuffix = addedText.slice(addedText.length - suffixLength)

  const removedSegments: DiffSegment[] = []
  const addedSegments: DiffSegment[] = []

  if (removedPrefix) {
    removedSegments.push({ text: removedPrefix, changed: false })
  }
  if (removedChanged) {
    removedSegments.push({ text: removedChanged, changed: true })
  }
  if (removedSuffix) {
    removedSegments.push({ text: removedSuffix, changed: false })
  }
  if (!removedSegments.length) {
    removedSegments.push({ text: "", changed: false })
  }

  if (addedPrefix) {
    addedSegments.push({ text: addedPrefix, changed: false })
  }
  if (addedChanged) {
    addedSegments.push({ text: addedChanged, changed: true })
  }
  if (addedSuffix) {
    addedSegments.push({ text: addedSuffix, changed: false })
  }
  if (!addedSegments.length) {
    addedSegments.push({ text: "", changed: false })
  }

  return { removedSegments, addedSegments }
}

function getInlineClass(type: DiffLine["type"]): string {
  if (type === "removed") {
    return "bg-rose-200/90 dark:bg-rose-700/70 text-rose-900 dark:text-rose-100 rounded-sm"
  }
  if (type === "added") {
    return "bg-emerald-200/90 dark:bg-emerald-700/70 text-emerald-900 dark:text-emerald-100 rounded-sm"
  }
  return ""
}

function createHeaderLine(content: string): DiffLine {
  return {
    type: "header",
    content,
    lineNum: null,
    segments: [{ text: content, changed: false }],
  }
}

// Parse unified diff and keep rows aligned side-by-side
const parsedDiff = computed((): DiffRow[] => {
  const rows: DiffRow[] = []

  if (!props.diffContent) {
    return rows
  }

  const lines = visibleDiffLines.value
  let leftLineNum = 1
  let rightLineNum = 1

  let pendingRemoved: DiffLine[] = []
  let pendingAdded: DiffLine[] = []

  const flushChangeBlock = () => {
    if (!pendingRemoved.length && !pendingAdded.length) {
      return
    }

    const maxLength = Math.max(pendingRemoved.length, pendingAdded.length)
    for (let index = 0; index < maxLength; index += 1) {
      const left = pendingRemoved[index] ?? null
      const right = pendingAdded[index] ?? null

      if (left && right) {
        const { removedSegments, addedSegments } = buildInlineSegments(left.content, right.content)
        left.segments = removedSegments
        right.segments = addedSegments
      } else if (left) {
        left.segments = [{ text: left.content, changed: true }]
      } else if (right) {
        right.segments = [{ text: right.content, changed: true }]
      }

      rows.push({ left, right })
    }

    pendingRemoved = []
    pendingAdded = []
  }

  for (const line of lines) {
    if (line === "") {
      continue
    }

    if (line.startsWith("@@")) {
      flushChangeBlock()

      const hunkMatch = line.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/)
      if (hunkMatch) {
        leftLineNum = Number(hunkMatch[1])
        rightLineNum = Number(hunkMatch[2])
      }

      rows.push({
        left: createHeaderLine(line),
        right: createHeaderLine(line),
      })
      continue
    }

    if (
      line.startsWith("diff --git")
      || line.startsWith("index ")
      || line.startsWith("---")
      || line.startsWith("+++")
      || line.startsWith("\\")
    ) {
      flushChangeBlock()
      rows.push({
        left: createHeaderLine(line),
        right: createHeaderLine(line),
      })
      continue
    }

    if (line.startsWith("-")) {
      pendingRemoved.push({
        type: "removed",
        content: line.substring(1),
        lineNum: leftLineNum,
        segments: [],
      })
      leftLineNum += 1
      continue
    }

    if (line.startsWith("+")) {
      pendingAdded.push({
        type: "added",
        content: line.substring(1),
        lineNum: rightLineNum,
        segments: [],
      })
      rightLineNum += 1
      continue
    }

    if (line.startsWith(" ")) {
      flushChangeBlock()
      const contextContent = line.substring(1)
      rows.push({
        left: {
          type: "context",
          content: contextContent,
          lineNum: leftLineNum,
          segments: [{ text: contextContent, changed: false }],
        },
        right: {
          type: "context",
          content: contextContent,
          lineNum: rightLineNum,
          segments: [{ text: contextContent, changed: false }],
        },
      })
      leftLineNum += 1
      rightLineNum += 1
      continue
    }

    flushChangeBlock()
    rows.push({
      left: createHeaderLine(line),
      right: createHeaderLine(line),
    })
  }

  flushChangeBlock()
  return rows
})

function getLineClass(type: string): string {
  switch (type) {
    case "removed":
      return "bg-rose-50 dark:bg-rose-950/30 border-l-4 border-rose-300 dark:border-rose-800"
    case "added":
      return "bg-emerald-50 dark:bg-emerald-950/30 border-l-4 border-emerald-300 dark:border-emerald-800"
    case "header":
      return "bg-slate-100 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-100 font-medium text-sm"
    default:
      return "bg-slate-50/70 dark:bg-slate-900/90 border-l-4 border-slate-200 dark:border-slate-700"
  }
}
</script>

<template>
  <div v-if="diffContent" class="space-y-4">
    <!-- Stats -->
    <div class="flex items-center space-x-6 text-sm">
      <span class="flex items-center space-x-2">
        <span class="text-green-600 dark:text-green-400 font-medium">+{{ linesAdded }}</span>
        <span class="text-gray-600 dark:text-gray-400">added</span>
      </span>
      <span class="flex items-center space-x-2">
        <span class="text-red-600 dark:text-red-400 font-medium">-{{ linesRemoved }}</span>
        <span class="text-gray-600 dark:text-gray-400">removed</span>
      </span>
    </div>

    <div v-if="isLargeDiff" class="flex flex-wrap items-center gap-3 text-sm">
      <p class="text-orange-600 dark:text-orange-400">
        Large diff detected ({{ diffLineCount }} lines).
        <span v-if="!showFullDiff">Showing first {{ MAX_DIFF_LINES }} lines.</span>
      </p>
      <button
        @click="showFullDiff = !showFullDiff"
        class="btn btn-secondary py-1 px-3 text-sm"
      >
        {{ showFullDiff ? "Hide full diff" : "Show full diff" }}
      </button>
    </div>

    <!-- Side-by-side diff viewer -->
    <div class="border border-slate-200 dark:border-slate-700 rounded-lg overflow-hidden">
      <div class="grid grid-cols-2 divide-x divide-slate-200 dark:divide-slate-700 bg-slate-100/90 dark:bg-slate-800/95 border-b border-slate-200 dark:border-slate-700">
        <div class="px-4 py-2 font-medium text-slate-700 dark:text-slate-100 text-xs">Original (Removed lines in red)</div>
        <div class="px-4 py-2 font-medium text-slate-700 dark:text-slate-100 text-xs">Modified (Added lines in green)</div>
      </div>

      <div class="font-mono text-sm bg-slate-50/50 dark:bg-slate-900 overflow-x-auto">
        <div class="min-w-5xl">
          <div
            v-for="(row, rowIndex) in parsedDiff"
            :key="`row-${rowIndex}`"
            class="grid grid-cols-2 divide-x divide-slate-200 dark:divide-slate-700"
          >
            <!-- Left side line -->
            <div v-if="row.left" :class="getLineClass(row.left.type)" class="flex min-h-7">
              <div
                v-if="row.left.type !== 'header'"
                class="shrink-0 w-14 px-3 py-1 text-right text-gray-500 dark:text-gray-400 bg-slate-100/70 dark:bg-slate-800/80 select-none border-r border-slate-200 dark:border-slate-700 text-xs"
              >
                {{ row.left.lineNum }}
              </div>
              <div v-else class="shrink-0 w-14" />
              <pre class="flex-1 px-4 py-1 text-gray-800 dark:text-gray-100 whitespace-pre-wrap break-all"><span
                v-for="(segment, segmentIndex) in row.left.segments"
                :key="`left-${rowIndex}-${segmentIndex}`"
                :class="segment.changed ? getInlineClass(row.left.type) : ''"
              >{{ segment.text }}</span></pre>
            </div>
            <div v-else class="flex min-h-7 bg-slate-50/60 dark:bg-slate-900/80 border-l-4 border-transparent">
              <div class="shrink-0 w-14 bg-slate-100/70 dark:bg-slate-800/80 border-r border-slate-200 dark:border-slate-700" />
              <pre class="flex-1 px-4 py-1" />
            </div>

            <!-- Right side line -->
            <div v-if="row.right" :class="getLineClass(row.right.type)" class="flex min-h-7">
              <div
                v-if="row.right.type !== 'header'"
                class="shrink-0 w-14 px-3 py-1 text-right text-gray-500 dark:text-gray-400 bg-slate-100/70 dark:bg-slate-800/80 select-none border-r border-slate-200 dark:border-slate-700 text-xs"
              >
                {{ row.right.lineNum }}
              </div>
              <div v-else class="shrink-0 w-14" />
              <pre class="flex-1 px-4 py-1 text-gray-800 dark:text-gray-100 whitespace-pre-wrap break-all"><span
                v-for="(segment, segmentIndex) in row.right.segments"
                :key="`right-${rowIndex}-${segmentIndex}`"
                :class="segment.changed ? getInlineClass(row.right.type) : ''"
              >{{ segment.text }}</span></pre>
            </div>
            <div v-else class="flex min-h-7 bg-slate-50/60 dark:bg-slate-900/80 border-l-4 border-transparent">
              <div class="shrink-0 w-14 bg-slate-100/70 dark:bg-slate-800/80 border-r border-slate-200 dark:border-slate-700" />
              <pre class="flex-1 px-4 py-1" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div v-else class="text-center text-gray-500 dark:text-gray-400 py-8">
    <p>No diff available</p>
    <p class="text-sm mt-1 text-gray-500 dark:text-gray-500">Select two commits to view differences</p>
  </div>
</template>
