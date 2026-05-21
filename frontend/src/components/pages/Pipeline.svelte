<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import { apiFetch } from '../../lib/api'

  interface Run {
    id: number
    source: string
    status: string
    message: string | null
    total: number
    processed: number
    skipped: number
    remaining: number
    pct_complete: number
    started_at: string
    finished_at: string | null
    resumed_from_id: number | null
  }

  let runs: Run[] = []
  let loading = true
  let pollInterval: ReturnType<typeof setInterval> | null = null

  const statusStyles: Record<string, string> = {
    running:  'bg-indigo-100 text-indigo-700',
    complete: 'bg-emerald-100 text-emerald-700',
    failed:   'bg-rose-100 text-rose-700',
  }

  async function load(): Promise<void> {
    const res = await apiFetch('/pipeline/runs')
    runs = await res!.json()
  }

  function startPolling(): void {
    if (pollInterval) return
    pollInterval = setInterval(async () => {
      await load()
      if (!runs.some(r => r.status === 'running')) stopPolling()
    }, 2000)
  }

  function stopPolling(): void {
    clearInterval(pollInterval ?? undefined)
    pollInterval = null
  }

  function fmt(iso: string): string {
    return new Date(iso).toLocaleString([], {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    })
  }

  function duration(run: Run): string {
    const end = run.finished_at ? new Date(run.finished_at) : new Date()
    const ms = end.getTime() - new Date(run.started_at).getTime()
    const s = Math.floor(ms / 1000)
    return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
  }

  onMount(async () => {
    await load()
    loading = false
    if (runs.some(r => r.status === 'running')) startPolling()
  })

  onDestroy(stopPolling)
</script>

<div class="p-8 flex flex-col gap-6">
  <div class="flex items-start justify-between">
    <div>
      <h2 class="text-xl font-bold text-surface-900">Pipeline Runs</h2>
      <p class="text-sm text-surface-400 mt-0.5">Airflow ingestion history with per-run progress</p>
    </div>
    <div class="flex items-center gap-3">
      {#if pollInterval}
        <span class="inline-flex items-center gap-1.5 text-xs text-indigo-500 font-medium">
          <span class="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse"></span>
          live
        </span>
      {/if}
      <button
        on:click={load}
        class="text-xs text-surface-400 hover:text-surface-700 bg-white border border-surface-200 px-3 py-1.5 rounded-xl transition-colors"
      >
        Refresh
      </button>
    </div>
  </div>

  <div class="bg-white rounded-2xl border border-surface-100 shadow-sm overflow-hidden">
    {#if loading}
      <div class="px-6 py-10 text-center text-sm text-surface-300">Loading…</div>
    {:else if runs.length === 0}
      <div class="px-6 py-10 text-center text-sm text-surface-300">No runs yet — trigger a DAG in Airflow.</div>
    {:else}
      <table class="w-full text-sm">
        <thead>
          <tr class="bg-surface-50 border-b border-surface-100">
            <th class="px-6 py-3 text-left text-xs font-semibold text-surface-500 uppercase tracking-wide">Source / Run</th>
            <th class="px-6 py-3 text-left text-xs font-semibold text-surface-500 uppercase tracking-wide">Status</th>
            <th class="px-6 py-3 text-left text-xs font-semibold text-surface-500 uppercase tracking-wide">Message</th>
            <th class="px-6 py-3 text-left text-xs font-semibold text-surface-500 uppercase tracking-wide">Progress</th>
            <th class="px-6 py-3 text-right text-xs font-semibold text-surface-500 uppercase tracking-wide">Total</th>
            <th class="px-6 py-3 text-right text-xs font-semibold text-surface-500 uppercase tracking-wide">Processed</th>
            <th class="px-6 py-3 text-right text-xs font-semibold text-surface-500 uppercase tracking-wide">Remaining</th>
            <th class="px-6 py-3 text-right text-xs font-semibold text-surface-500 uppercase tracking-wide">Skipped</th>
            <th class="px-6 py-3 text-left text-xs font-semibold text-surface-500 uppercase tracking-wide">Started</th>
            <th class="px-6 py-3 text-left text-xs font-semibold text-surface-500 uppercase tracking-wide">Duration</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-surface-50">
          {#each runs as run}
            <tr class="hover:bg-surface-50/60 transition-colors">
              <td class="px-6 py-3.5">
                <span class="font-medium text-surface-800">{run.source.replace(/_/g, ' ')}</span>
                <div class="flex items-center gap-1.5 mt-0.5">
                  <span class="text-xs text-surface-400 font-mono">#{run.id}</span>
                  {#if run.resumed_from_id !== null}
                    <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium bg-violet-50 text-violet-600">
                      <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                      resumed from #{run.resumed_from_id}
                    </span>
                  {/if}
                </div>
              </td>
              <td class="px-6 py-3.5">
                <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold {statusStyles[run.status] ?? 'bg-surface-100 text-surface-500'}">
                  {#if run.status === 'running'}
                    <span class="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse"></span>
                  {/if}
                  {run.status}
                </span>
              </td>
              <td class="px-6 py-3.5 text-xs max-w-xs">
                {#if run.message}
                  <span class="text-rose-500 font-mono">{run.message}</span>
                {:else}
                  <span class="text-surface-300">—</span>
                {/if}
              </td>
              <td class="px-6 py-3.5 w-40">
                <div class="flex items-center gap-2">
                  <div class="flex-1 bg-surface-100 rounded-full h-1.5">
                    <div
                      class="h-1.5 rounded-full transition-all duration-500
                        {run.status === 'running' ? 'bg-indigo-400' : run.status === 'complete' ? 'bg-emerald-500' : 'bg-rose-400'}"
                      style="width: {run.pct_complete}%"
                    ></div>
                  </div>
                  <span class="text-xs text-surface-500 tabular-nums w-10 text-right">{run.pct_complete}%</span>
                </div>
              </td>
              <td class="px-6 py-3.5 text-right text-surface-600 tabular-nums">{run.total.toLocaleString()}</td>
              <td class="px-6 py-3.5 text-right text-surface-600 tabular-nums">{run.processed.toLocaleString()}</td>
              <td class="px-6 py-3.5 text-right tabular-nums {run.remaining > 0 && run.status === 'running' ? 'text-amber-600 font-medium' : 'text-surface-400'}">
                {run.remaining.toLocaleString()}
              </td>
              <td class="px-6 py-3.5 text-right text-surface-400 tabular-nums">{run.skipped.toLocaleString()}</td>
              <td class="px-6 py-3.5 text-xs text-surface-400">{fmt(run.started_at)}</td>
              <td class="px-6 py-3.5 text-xs text-surface-400 tabular-nums">{duration(run)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>
</div>
