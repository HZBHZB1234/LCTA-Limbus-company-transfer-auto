<script setup lang="ts">
</script>

<template>
  <div>
    <div class="section-header">
      <h2 class="section-title"><i class="fas fa-flask"></i> 测试界面</h2>
      <p class="section-subtitle">开发和调试工具</p>
    </div>
    <div class="setting-card">
      <p style="color: var(--text-secondary)">测试功能区域。正常运行不需要使用此页面。</p>
    </div>
  </div>
</template>

<style scoped>
.section-header { margin-bottom: 24px; }
.section-title { font-size: 22px; font-weight: 600; display: flex; align-items: center; gap: 10px; }
.section-title i { color: var(--accent-color); }
.section-subtitle { color: var(--text-secondary); font-size: 14px; margin-top: 4px; }
.setting-card { background: var(--bg-secondary); border-radius: 12px; padding: 20px; border: 1px solid var(--border-color); max-width: 500px; }
</style>
