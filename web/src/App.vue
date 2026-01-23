<template>
  <el-container class="layout-container" :class="{ 'is-login': isLogin }">
    <el-header v-if="!isLogin" class="header">
      <div class="header-inner">
        <div class="header-left">
          <el-button v-if="isMobile" class="menu-btn" @click="drawerVisible = true">菜单</el-button>
          <div class="logo">{{ isMobile ? '工学云' : '工学云管理平台' }}</div>
        </div>

        <div class="header-actions">
          <template v-if="!isMobile">
            <el-button v-if="isAuthed" @click="go('/')">用户</el-button>
            <el-button v-if="isAuthed && isAdmin" @click="go('/audit')">审计日志</el-button>
            <el-button v-if="isAuthed && isAdmin" @click="go('/admins')">账号管理</el-button>
            <el-switch
              v-model="isDark"
              inline-prompt
              active-text="暗色"
              inactive-text="亮色"
              @change="applyTheme"
            />
            <el-tag v-if="isAuthed" size="small" type="info">{{ roleLabel }}</el-tag>
            <el-button v-if="isAuthed" type="danger" plain @click="logout">退出</el-button>
          </template>

          <template v-else>
            <el-switch v-model="isDark" inline-prompt active-text="暗" inactive-text="亮" @change="applyTheme" />
          </template>
        </div>
      </div>
    </el-header>
    <el-main>
      <div class="page" :class="{ 'is-login-page': isLogin }">
        <router-view />
      </div>
    </el-main>

    <el-drawer v-if="!isLogin" v-model="drawerVisible" title="菜单" direction="rtl" size="80%">
      <div class="drawer-body">
        <div v-if="isAuthed" class="drawer-user">
          <div class="drawer-user-name">{{ username || '已登录' }}</div>
          <el-tag size="small" type="info">{{ roleLabel }}</el-tag>
        </div>

        <div class="drawer-actions">
          <el-button v-if="isAuthed" style="width: 100%" @click="navTo('/')">用户</el-button>
          <el-button v-if="isAuthed && isAdmin" style="width: 100%" @click="navTo('/audit')">审计日志</el-button>
          <el-button v-if="isAuthed && isAdmin" style="width: 100%" @click="navTo('/admins')">账号管理</el-button>
        </div>

        <div class="drawer-section">
          <div class="drawer-section-title">主题</div>
          <el-switch v-model="isDark" inline-prompt active-text="暗" inactive-text="亮" @change="applyTheme" />
        </div>

        <div class="drawer-footer">
          <el-button v-if="isAuthed" type="danger" plain style="width: 100%" @click="logout">退出登录</el-button>
        </div>
      </div>
    </el-drawer>
  </el-container>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'

const isDark = ref(false)
const isMobile = ref(false)
const drawerVisible = ref(false)
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const isAuthed = computed(() => auth.isAuthed)
const isAdmin = computed(() => auth.isAdmin)
const username = computed(() => auth.username)
const isLogin = computed(() => route.path === '/login')
const roleLabel = computed(() => {
  if (auth.role === 'admin') return '管理员'
  if (auth.role === 'operator') return '操作员'
  if (auth.role === 'viewer') return '只读'
  return '未知'
})

const applyTheme = () => {
  const on = !!isDark.value
  document.documentElement.classList.toggle('dark', on)
  localStorage.setItem('theme', on ? 'dark' : 'light')
}

const go = (path) => {
  router.push(path)
}

const navTo = (path) => {
  drawerVisible.value = false
  router.push(path)
}

const logout = () => {
  drawerVisible.value = false
  auth.logout()
  router.replace('/login')
}

let removeMqListener = null

onMounted(() => {
  const saved = localStorage.getItem('theme')
  if (saved === 'dark' || saved === 'light') {
    isDark.value = saved === 'dark'
  } else {
    isDark.value = window.matchMedia?.('(prefers-color-scheme: dark)')?.matches || false
  }
  applyTheme()

  const mq = window.matchMedia?.('(max-width: 768px)')
  const update = () => {
    isMobile.value = !!mq?.matches
    if (!isMobile.value) drawerVisible.value = false
  }
  update()
  mq?.addEventListener?.('change', update)
  removeMqListener = () => mq?.removeEventListener?.('change', update)
})

onUnmounted(() => removeMqListener?.())
</script>

<style>
body {
  margin: 0;
  background-color: var(--el-bg-color-page);
  color: var(--el-text-color-primary);
}
.el-card {
  border-radius: 12px;
}
.el-card__header {
  padding: 14px 16px;
}
.el-card__body {
  padding: 16px;
}
.page-card > .el-card__header {
  padding: 14px 16px;
}
.page-card > .el-card__body {
  padding: 16px;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.page-title {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.page-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}
.page-actions .el-input {
  min-width: 200px;
}
.table-wrap {
  width: 100%;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
.table-wrap > .el-table {
  min-width: 860px;
}
.el-main {
  padding: 16px;
  padding-bottom: calc(16px + env(safe-area-inset-bottom));
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  min-height: 0;
}
.layout-container {
  height: 100vh;
  height: 100dvh;
}
.layout-container.is-login .el-main {
  padding: 0;
  padding-bottom: env(safe-area-inset-bottom);
}
.header {
  background-color: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color);
  display: flex;
  align-items: center;
  padding: 0 calc(12px + env(safe-area-inset-left)) 0 calc(12px + env(safe-area-inset-right));
  height: 56px;
}
.header-inner {
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.logo {
  font-size: 20px;
  font-weight: bold;
  color: #409eff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.menu-btn {
  padding: 0 10px;
}
.page {
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
}
.page.is-login-page {
  max-width: none;
  margin: 0;
}
.drawer-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.drawer-user {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.drawer-user-name {
  font-weight: 600;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.drawer-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.drawer-section-title {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}
.drawer-footer {
  margin-top: auto;
  padding-bottom: env(safe-area-inset-bottom);
}
@media (max-width: 768px) {
  .el-main {
    padding: 12px;
    padding-bottom: calc(12px + env(safe-area-inset-bottom));
  }
  .layout-container.is-login .el-main {
    padding: 0;
    padding-bottom: env(safe-area-inset-bottom);
  }
  .page-header {
    flex-direction: column;
    align-items: stretch;
  }
  .page-actions {
    justify-content: stretch;
    width: 100%;
  }
  .page-actions .el-input {
    flex: 1 1 100%;
    min-width: 0;
  }
  .table-wrap > .el-table {
    min-width: 780px;
  }
  .logo {
    font-size: 18px;
  }
  .header {
    height: 50px;
  }
  .header-actions {
    gap: 8px;
  }
}
</style>
