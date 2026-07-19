<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AppSidebar from '@/components/AppSidebar.vue'
import ModalContainer from '@/components/ModalContainer.vue'
import HelpDrawer from '@/components/HelpDrawer.vue'
import DragOverlay from '@/components/DragOverlay.vue'
import { useConfigStore } from '@/stores/config'
import { useModalStore } from '@/stores/modal'
import { useLogStore } from '@/stores/log'
import { useThemeStore } from '@/stores/theme'
import { useUpdateStore } from '@/stores/update'

const router = useRouter()
const configStore = useConfigStore()
const modalStore = useModalStore()
const logStore = useLogStore()
const themeStore = useThemeStore()
const updateStore = useUpdateStore()

onMounted(() => {
  themeStore.init()
  modalStore.setupEventListeners()
  logStore.setupEventListeners()

  if (configStore.firstUse) {
    router.push('/welcome')
  } else {
    const autoCheck = configStore.get<boolean>('auto_check_update') !== false
    if (autoCheck) {
      updateStore.check().then(() => {
        if (updateStore.hasUpdate) {
          updateStore.showUpdateModal()
        }
      })
    }
  }
})
</script>

<template>
  <div class="app-root">
    <AppSidebar />
    <div class="main-content">
      <router-view v-slot="{ Component }">
        <transition name="page-fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </div>
    <ModalContainer />
    <HelpDrawer />
    <DragOverlay />
  </div>
</template>

<style>
/* App-level global overrides — theme tokens are in @/assets/main.css */
</style>
