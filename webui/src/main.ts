import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { initApi } from './utils/api'
import { useConfigStore } from './stores/config'

import '@fortawesome/fontawesome-free/css/all.min.css'

async function bootstrap() {
  await initApi()

  const app = createApp(App)
  const pinia = createPinia()
  app.use(pinia)
  app.use(router)

  const configStore = useConfigStore()
  await configStore.init()

  app.mount('#app')
}

bootstrap()
