<template>
  <div class="page">
    <el-card class="page-card" shadow="never">
      <template #header>
        <div class="header">
          <div>
            <div class="title">我的配置</div>
            <div class="sub">修改后会影响打卡/报告执行</div>
          </div>
          <div class="actions">
            <el-button size="small" :loading="loading" @click="load">刷新</el-button>
            <el-button size="small" type="primary" :loading="saving" @click="save">保存</el-button>
            <el-button size="small" @click="back">返回</el-button>
          </div>
        </div>
      </template>

      <el-form label-width="92px" v-loading="loading">
        <el-divider>账号</el-divider>
        <el-form-item label="工学云账号">
          <template v-if="bound">
            <div class="bind-row">
              <el-input :model-value="me.phone" readonly />
              <el-button class="bind-action" @click="startRebind">更换绑定</el-button>
            </div>
          </template>
          <template v-else>
            <div class="bind-form">
              <el-input v-model="bindPhone" placeholder="请输入工学云账号/手机号" autocomplete="username" />
              <el-input
                v-model="bindPassword"
                type="password"
                show-password
                placeholder="请输入工学云密码"
                autocomplete="current-password"
              />
              <el-button type="primary" :loading="binding" @click="bind">绑定</el-button>
            </div>
            <div class="bind-hint">平台登录账号仅用于进入用户端，绑定工学云账号后才能执行打卡/报告。</div>
          </template>
        </el-form-item>
        <el-form-item v-if="bound" label="工学云密码">
          <el-input v-model="password" type="password" show-password placeholder="留空表示不修改（用于打卡/报告登录）" />
        </el-form-item>

        <el-divider>打卡</el-divider>
        <el-form-item label="启用打卡">
          <el-switch v-model="clockInEnabled" />
        </el-form-item>
        <el-form-item label="打卡地址">
          <div class="address-row">
            <el-input v-model="clockInAddress" placeholder="请输入详细地址" />
            <el-button @click="autoFillAddress" :loading="addressLoading" type="success" plain>自动获取</el-button>
          </div>
        </el-form-item>
        <el-form-item label="上班时间">
          <el-time-picker v-model="startTime" value-format="HH:mm" format="HH:mm" />
        </el-form-item>
        <el-form-item label="下班时间">
          <el-time-picker v-model="endTime" value-format="HH:mm" format="HH:mm" />
        </el-form-item>

        <el-divider>报告</el-divider>
        <el-form-item label="启用日报">
          <el-switch v-model="dailyEnabled" />
        </el-form-item>
        <el-form-item v-if="dailyEnabled" label="日报提交时间">
          <el-time-select v-model="dailySubmitTime" start="00:00" step="00:01" end="23:59" />
        </el-form-item>
        <el-form-item label="启用周报">
          <el-switch v-model="weeklyEnabled" />
        </el-form-item>
        <el-form-item label="启用月报">
          <el-switch v-model="monthlyEnabled" />
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { userHttp } from '../../api/userHttp'
import { notifySuccess, notifyError, resolveErrorMessage } from '../../utils/notify'

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const me = ref({ phone: '' })
const bound = ref(false)

const bindPhone = ref('')
const bindPassword = ref('')
const binding = ref(false)

const password = ref('')
const clockInEnabled = ref(true)
const clockInAddress = ref('')
const addressLoading = ref(false)
const startTime = ref('07:30')
const endTime = ref('18:00')
const dailyEnabled = ref(false)
const dailySubmitTime = ref('12:00')
const weeklyEnabled = ref(false)
const monthlyEnabled = ref(false)

const _ensureObj = (v) => (v && typeof v === 'object' ? v : {})

const startRebind = () => {
  bound.value = false
  bindPhone.value = ''
  bindPassword.value = ''
}

const bind = async () => {
  const phone = String(bindPhone.value || '').trim()
  const pw = String(bindPassword.value || '').trim()
  if (!phone || phone.length < 4) {
    notifyError('请填写正确的工学云账号')
    return
  }
  if (!pw || pw.length < 6) {
    notifyError('工学云密码至少 6 位')
    return
  }
  binding.value = true
  try {
    await userHttp.post('/app/bind', { task_phone: phone, task_password: pw })
    bindPassword.value = ''
    notifySuccess('绑定成功')
    await load()
  } catch (e) {
    notifyError(resolveErrorMessage(e, '绑定失败'))
  } finally {
    binding.value = false
  }
}

const autoFillAddress = async () => {
  if (!bound.value) {
    notifyError('请先绑定工学云账号')
    return
  }
  addressLoading.value = true
  try {
    const res = await userHttp.get('/app/account-address')
    if (res.data?.address) {
      clockInAddress.value = res.data.address
      notifySuccess('已自动填充打卡地址')
    } else {
      notifyError('未获取到有效地址')
    }
  } catch (e) {
    notifyError(resolveErrorMessage(e, '获取地址失败'))
  } finally {
    addressLoading.value = false
  }
}

const load = async () => {
  loading.value = true
  try {
    const res = await userHttp.get('/app/me')
    bound.value = !!res.data?.bound
    me.value = bound.value ? (res.data?.task_user || {}) : { phone: '' }
    const ci = _ensureObj(me.value.clockIn)
    const loc = _ensureObj(ci.location)
    const schedule = _ensureObj(ci.schedule)
    clockInEnabled.value = me.value.enable_clockin !== false
    clockInAddress.value = String(loc.address || '')
    startTime.value = String(schedule.startTime || '07:30')
    endTime.value = String(schedule.endTime || '18:00')
    const rs = _ensureObj(me.value.reportSettings)
    dailyEnabled.value = !!_ensureObj(rs.daily).enabled
    dailySubmitTime.value = String(_ensureObj(rs.daily).submitTime || '12:00')
    weeklyEnabled.value = !!_ensureObj(rs.weekly).enabled
    monthlyEnabled.value = !!_ensureObj(rs.monthly).enabled
  } catch (e) {
    notifyError(resolveErrorMessage(e, '加载失败'))
  } finally {
    loading.value = false
  }
}

const save = async () => {
  if (!bound.value) {
    notifyError('请先绑定工学云账号')
    return
  }
  const clockIn = _ensureObj(me.value.clockIn)
  const location = _ensureObj(clockIn.location)
  const schedule = _ensureObj(clockIn.schedule)
  location.address = String(clockInAddress.value || '').trim()
  schedule.startTime = String(startTime.value || '07:30')
  schedule.endTime = String(endTime.value || '18:00')
  clockIn.location = location
  clockIn.schedule = schedule

  const reportSettings = _ensureObj(me.value.reportSettings)
  reportSettings.daily = {
    ..._ensureObj(reportSettings.daily),
    enabled: !!dailyEnabled.value,
    submitTime: String(dailySubmitTime.value || '12:00'),
  }
  reportSettings.weekly = { ..._ensureObj(reportSettings.weekly), enabled: !!weeklyEnabled.value }
  reportSettings.monthly = { ..._ensureObj(reportSettings.monthly), enabled: !!monthlyEnabled.value }

  saving.value = true
  try {
    await userHttp.patch('/app/me', {
      password: String(password.value || '').trim() || undefined,
      clockIn,
      reportSettings,
    })
    password.value = ''
    notifySuccess('已保存')
    await load()
  } catch (e) {
    notifyError(resolveErrorMessage(e, '保存失败'))
  } finally {
    saving.value = false
  }
}

const back = () => router.push('/u')

load()
</script>

<style scoped>
.page {
  padding: 14px 12px;
}
.bind-row {
  width: 100%;
  display: flex;
  gap: 10px;
  align-items: center;
}
.bind-action {
  flex: 0 0 auto;
}
.bind-form {
  width: 100%;
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.bind-form :deep(.el-input) {
  flex: 1 1 160px;
}
.bind-hint {
  width: 100%;
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
.address-row {
  width: 100%;
  display: flex;
  gap: 10px;
}
.header {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.title {
  font-weight: 700;
  font-size: 16px;
}
.sub {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
