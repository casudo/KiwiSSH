<script setup lang="ts">
import { computed } from "vue"

interface DiffLine {
  type: "context" | "added" | "removed" | "header"
  content: string
  lineNum?: string
}

interface Props {
  diffContent: string
  linesAdded: number
  linesRemoved: number
}

const props = defineProps<Props>()

// Parse unified diff format
const parsedDiff = computed((): { left: DiffLine[]; right: DiffLine[] } => {
  const leftLines: DiffLine[] = []
  const rightLines: DiffLine[] = []

  if (!props.diffContent) return { left: leftLines, right: rightLines }

  const lines = props.diffContent.split("\n")
  let leftLineNum = 0
  let rightLineNum = 0

  for (const line of lines) {
    if (line.startsWith("---") || line.startsWith("+++") || line.startsWith("@@")) {
      // Header lines - show on both sides
      leftLines.push({ type: "header", content: line })
      rightLines.push({ type: "header", content: line })
    } else if (line.startsWith("-")) {
      // Removed line - show only on left
      leftLines.push({
        type: "removed",
        content: line.substring(1),
        lineNum: String(leftLineNum++),
      })
    } else if (line.startsWith("+")) {
      // Added line - show only on right
      rightLines.push({
        type: "added",
        content: line.substring(1),
        lineNum: String(rightLineNum++),
      })
    } else if (line === "") {
      // Empty line
      leftLines.push({ type: "context", content: "", lineNum: String(leftLineNum++) })
      rightLines.push({ type: "context", content: "", lineNum: String(rightLineNum++) })
    } else {
      // Context line (unchanged)
      leftLines.push({ type: "context", content: line.substring(1), lineNum: String(leftLineNum++) })
      rightLines.push({ type: "context", content: line.substring(1), lineNum: String(rightLineNum++) })
    }
  }

  return { left: leftLines, right: rightLines }
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

    <!-- Side-by-side diff viewer -->
    <div class="border border-slate-200 dark:border-slate-700 rounded-lg overflow-hidden">
      <div class="grid grid-cols-1 lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x divide-slate-200 dark:divide-slate-700">
        <!-- Left side (From/Removed) -->
        <div class="font-mono text-sm bg-slate-50/50 dark:bg-slate-900 overflow-x-auto">
          <div class="min-w-max">
            <div class="sticky top-0 bg-slate-100/90 dark:bg-slate-800/95 border-b border-slate-200 dark:border-slate-700 px-4 py-2 font-medium text-slate-700 dark:text-slate-100 text-xs">
              Original (Removed lines in red)
            </div>
            <div
              v-for="(line, idx) in parsedDiff.left"
              :key="`left-${idx}`"
              :class="getLineClass(line.type)"
              class="flex"
            >
              <div v-if="line.type !== 'header'" class="flex-shrink-0 w-12 px-3 py-1 text-right text-gray-500 dark:text-gray-400 bg-slate-100/70 dark:bg-slate-800/80 select-none border-r border-slate-200 dark:border-slate-700 text-xs">
                {{ line.lineNum }}
              </div>
              <div v-else class="flex-shrink-0 w-12" />
              <pre class="flex-1 px-4 py-1 text-gray-800 dark:text-gray-100 whitespace-pre-wrap break-words">{{
                line.content
              }}</pre>
            </div>
          </div>
        </div>

        <!-- Right side (To/Added) -->
        <div class="font-mono text-sm bg-slate-50/50 dark:bg-slate-900 overflow-x-auto">
          <div class="min-w-max">
            <div class="sticky top-0 bg-slate-100/90 dark:bg-slate-800/95 border-b border-slate-200 dark:border-slate-700 px-4 py-2 font-medium text-slate-700 dark:text-slate-100 text-xs">
              Modified (Added lines in green)
            </div>
            <div
              v-for="(line, idx) in parsedDiff.right"
              :key="`right-${idx}`"
              :class="getLineClass(line.type)"
              class="flex"
            >
              <div v-if="line.type !== 'header'" class="flex-shrink-0 w-12 px-3 py-1 text-right text-gray-500 dark:text-gray-400 bg-slate-100/70 dark:bg-slate-800/80 select-none border-r border-slate-200 dark:border-slate-700 text-xs">
                {{ line.lineNum }}
              </div>
              <div v-else class="flex-shrink-0 w-12" />
              <pre class="flex-1 px-4 py-1 text-gray-800 dark:text-gray-100 whitespace-pre-wrap break-words">{{
                line.content
              }}</pre>
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
