<template>
  <div class="login-page">
    <el-card class="login-card page-card">
      <template #header>
        <div class="login-header">
          <div class="login-title">工学云管理平台</div>
          <div class="login-subtitle">后台登录</div>
        </div>
      </template>
      <el-form :model="form" @keyup.enter="submit">
        <el-form-item label="账号">
          <el-input v-model="form.username" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password autocomplete="current-password" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" style="width: 100%" @click="submit">登录</el-button>
        </el-form-item>
      </el-form>
      <div class="login-hint">
        默认账号：admin / admin123456；operator / operator123456；viewer / viewer123456（建议上线后通过环境变量修改）
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { http } from '../api/http'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const form = reactive({
  username: auth.username || 'admin',
  password: '',
})

const submit = async () => {
  loading.value = true
  try {
    const res = await http.post('/auth/login', {
      username: form.username?.trim(),
      password: form.password?.trim(),
    })
    auth.setAuth(res.data.token, res.data.username, res.data.role)
    ElMessage.success('登录成功')
    router.replace('/')
  } catch (e) {
    ElMessage.error(e.friendlyMessage || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  min-height: 100dvh;
  padding: 16px;
  background:
    radial-gradient(900px 360px at 20% 10%, rgba(64, 158, 255, 0.12), transparent 60%),
    radial-gradient(900px 360px at 80% 0%, rgba(103, 194, 58, 0.10), transparent 55%),
    var(--el-bg-color-page);
}
.login-card {
  width: 420px;
  max-width: 92vw;
}
.login-header {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.login-title {
  font-weight: 800;
  letter-spacing: 0.2px;
}
.login-subtitle {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.login-hint {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
:global(html.dark) .login-page {
  background:
    radial-gradient(900px 360px at 20% 10%, rgba(64, 158, 255, 0.16), transparent 60%),
    radial-gradient(900px 360px at 80% 0%, rgba(103, 194, 58, 0.12), transparent 55%),
    var(--el-bg-color-page);
}
</style>
