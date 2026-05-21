<script lang="ts">
  import type { ComponentType } from 'svelte'
  import { isAuthenticated } from './lib/auth'
  import Login from './components/Login.svelte'
  import Sidebar from './components/layout/Sidebar.svelte'
  import Dashboard from './components/pages/Dashboard.svelte'
  import Customers from './components/pages/Customers.svelte'
  import Products from './components/pages/Products.svelte'
  import Orders from './components/pages/Orders.svelte'
  import Jobs from './components/pages/Jobs.svelte'
  import Pipeline from './components/pages/Pipeline.svelte'
  import Stores from './components/pages/Stores.svelte'

  type PageKey = 'dashboard' | 'customers' | 'products' | 'orders' | 'jobs' | 'stores' | 'pipeline'

  let currentPage: PageKey = 'dashboard'

  const pages: Record<PageKey, ComponentType> = {
    dashboard: Dashboard,
    customers: Customers,
    products: Products,
    orders: Orders,
    jobs: Jobs,
    pipeline: Pipeline,
    stores: Stores,
  }
</script>

{#if $isAuthenticated}
  <div class="flex min-h-screen bg-surface-50">
    <Sidebar current={currentPage} onNavigate={p => currentPage = p} />
    <main class="flex-1 overflow-auto">
      <svelte:component this={pages[currentPage]} />
    </main>
  </div>
{:else}
  <Login />
{/if}
