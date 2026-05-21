<script lang="ts">
  import { logout } from '../../lib/auth'
  import { jobCounts } from '../../lib/jobs'

  type PageKey = 'dashboard' | 'customers' | 'products' | 'orders' | 'jobs' | 'stores' | 'pipeline'
  interface NavLink { key: PageKey; label: string; icon: string }

  export let current: PageKey = 'dashboard'
  export let onNavigate: (page: PageKey) => void = () => {}

  const links: NavLink[] = [
    {
      key: 'dashboard',
      label: 'Dashboard',
      icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6',
    },
    {
      key: 'customers',
      label: 'Customers',
      icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z',
    },
    {
      key: 'products',
      label: 'Products',
      icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4',
    },
    {
      key: 'orders',
      label: 'Orders',
      icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01',
    },
    {
      key: 'stores',
      label: 'Stores',
      icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6',
    },
    {
      key: 'pipeline',
      label: 'Pipeline',
      icon: 'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15',
    },
    {
      key: 'jobs',
      label: 'Jobs',
      icon: 'M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z',
    },
  ]
</script>

<aside class="w-56 shrink-0 bg-surface-900 min-h-screen flex flex-col">
  <div class="px-4 py-5">
    <div class="flex items-center gap-3">
      <div class="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-400 to-violet-500 flex items-center justify-center shrink-0 shadow-lg shadow-indigo-500/30">
        <svg class="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2" />
        </svg>
      </div>
      <span class="text-white font-semibold tracking-tight">Databridge</span>
    </div>
  </div>

  <div class="px-4 mb-1">
    <p class="text-xs font-semibold text-surface-600 uppercase tracking-widest px-2 mb-1">Menu</p>
  </div>

  <nav class="flex flex-col gap-0.5 px-3 flex-1">
    {#each links as link}
      <button
        on:click={() => onNavigate(link.key)}
        class="w-full text-left px-3 py-2.5 rounded-xl text-sm transition-all flex items-center gap-3
          {current === link.key
            ? 'bg-indigo-500 text-white font-medium shadow-lg shadow-indigo-500/20'
            : 'text-surface-400 hover:bg-surface-800 hover:text-white'}"
      >
        <svg class="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.75">
          <path stroke-linecap="round" stroke-linejoin="round" d={link.icon} />
        </svg>
        {link.label}
        {#if link.key === 'jobs'}
          <span class="ml-auto flex items-center gap-1">
            {#if $jobCounts.active > 0}
              <span class="text-xs font-semibold bg-amber-500/70 text-amber-50 rounded-full w-5 h-5 flex items-center justify-center">
                {$jobCounts.active}
              </span>
            {/if}
            {#if $jobCounts.failed > 0}
              <span class="text-xs font-semibold bg-rose-500/70 text-rose-50 rounded-full w-5 h-5 flex items-center justify-center">
                {$jobCounts.failed}
              </span>
            {/if}
          </span>
        {/if}
      </button>
    {/each}
  </nav>

  <div class="px-4 py-4 border-t border-surface-800 flex flex-col gap-1">
    <a
      href="https://github.com/gretschduojet1/databridge"
      target="_blank"
      rel="noreferrer"
      class="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-surface-500 hover:bg-surface-800 hover:text-white transition-all"
    >
      <svg class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2C6.477 2 2 6.477 2 12c0 4.418 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.009-.868-.013-1.703-2.782.604-3.369-1.34-3.369-1.34-.454-1.156-1.11-1.463-1.11-1.463-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.578 9.578 0 0112 6.836c.85.004 1.705.114 2.504.336 1.909-1.294 2.747-1.025 2.747-1.025.546 1.377.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.578.688.48C19.138 20.163 22 16.418 22 12c0-5.523-4.477-10-10-10z" />
      </svg>
      GitHub
    </a>
    <button
      on:click={logout}
      class="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-surface-500 hover:bg-surface-800 hover:text-white transition-all"
    >
      <svg class="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.75">
        <path stroke-linecap="round" stroke-linejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
      </svg>
      Sign out
    </button>
  </div>
</aside>
