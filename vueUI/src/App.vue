<template>
  <div class="app-container" :class="`theme-${themeStore.currentTheme}`">
    <ThemeToggle />
    <Sidebar />
    <div class="main-content">
      <router-view v-slot="{ Component }">
        <transition name="fade-slide" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </div>
    <ModalContainer />
    <DragOverlay />
  </div>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import ThemeToggle from '@/components/common/ThemeToggle.vue'
import Sidebar from '@/components/common/Sidebar.vue'
import ModalContainer from '@/components/modal/ModalContainer.vue'
import DragOverlay from '@/components/drag/DragOverlay.vue'
import { useThemeStore } from '@/stores/theme'
import { useDragDropStore } from '@/stores/dragDrop'

const themeStore = useThemeStore()
const dragDropStore = useDragDropStore()

onMounted(() => {
  // 初始化拖拽管理器
  dragDropStore.init()
})

onUnmounted(() => {
  dragDropStore.destroy()
})
</script>

<style scoped>
.app-container {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background-color: var(--color-bg-primary);
  transition: background-color var(--transition-speed) var(--transition-easing);
}

.main-content {
  flex: 1;
  padding: var(--spacing-lg);
  overflow-y: auto;
  background: var(--color-bg-primary);
}

/* 路由过渡动画 */
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.3s ease;
}
.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(20px);
}
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-20px);
}
</style>