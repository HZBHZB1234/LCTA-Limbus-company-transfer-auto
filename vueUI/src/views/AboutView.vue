<template>
  <div class="about-view">
    <div class="section-header">
      <h2 class="section-title">
        <i class="fas fa-info-circle"></i> 关于 LCTA
      </h2>
      <p class="section-subtitle">边狱公司汉化工具箱</p>
    </div>

    <div class="about-container">
      <div class="about-card">
        <div class="about-header">
          <div class="about-logo"><i class="fas fa-language"></i></div>
          <div class="about-title">
            <h3>LCTA - 边狱公司汉化工具箱</h3>
            <p class="version-badge">版本 4.1.5</p>
          </div>
        </div>
        <MarkdownRenderer :url="'/assets/README.md'" />
      </div>

      <div class="about-card">
        <div class="about-header">
          <div class="about-logo"><i class="fas fa-history"></i></div>
          <div class="about-title">
            <h3>更新内容</h3>
            <p class="version-badge">版本 4.1.5</p>
          </div>
        </div>
        <MarkdownRenderer :url="'/assets/update.md'" />
      </div>

      <div class="about-card">
        <div class="about-header">
          <div class="about-logo"><i class="fas fa-question-circle"></i></div>
          <div class="about-title">
            <h3>引导</h3>
            <p class="version-badge">首次使用必读</p>
          </div>
        </div>
        <MarkdownRenderer :url="'/assets/firstUse.md'" />
      </div>
    </div>
  </div>
</template>

<script setup>
import MarkdownRenderer from '@/components/common/MarkdownRenderer.vue'
</script>

<style scoped>
.section-header {
  margin-bottom: var(--spacing-xl);
  padding-bottom: var(--spacing-md);
  border-bottom: 2px solid var(--color-border-light);
}
.section-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--color-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}
.section-subtitle {
  color: var(--color-text-secondary);
  font-size: 16px;
}
.about-container {
  max-width: 800px;
  margin: 0 auto;
}
.about-card {
  background: var(--color-bg-card);
  border-radius: var(--radius-lg);
  padding: var(--spacing-xl);
  box-shadow: var(--shadow-md);
  border: 1px solid var(--color-border);
  margin-bottom: var(--spacing-lg);
}
.about-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-xl);
  padding-bottom: var(--spacing-lg);
  border-bottom: 2px solid var(--color-border-light);
}
.about-logo {
  width: 80px;
  height: 80px;
  background: linear-gradient(135deg, var(--color-primary), var(--color-secondary));
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 32px;
}
.about-title h3 {
  font-size: 24px;
  margin-bottom: var(--spacing-xs);
  color: var(--color-primary);
}
.version-badge {
  display: inline-block;
  background: var(--color-primary);
  color: white;
  padding: 4px 12px;
  border-radius: var(--radius-sm);
  font-size: 12px;
}
</style>