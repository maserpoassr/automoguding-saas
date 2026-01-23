<template>
  <el-card class="page-card">
    <template #header>
      <div class="page-header">
        <div class="page-title">{{ isEdit ? '编辑用户' : '添加用户' }}</div>
        <div class="page-actions">
          <el-button @click="$router.back()">返回</el-button>
        </div>
      </div>
    </template>

    <el-form
      :model="form"
      :label-width="isMobile ? 'auto' : '120px'"
      :label-position="isMobile ? 'top' : 'right'"
      v-loading="loading"
    >
      <el-tabs v-model="activeTab">
        <el-tab-pane label="基本信息" name="basic">
          <el-form-item label="账号">
            <el-input v-model="form.phone" placeholder="请输入工学云账号" />
          </el-form-item>
          <el-form-item label="密码">
            <el-input v-model="form.password" type="password" show-password :placeholder="passwordPlaceholder" />
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="form.remark" type="textarea" :rows="2" placeholder="例如：张三/研发部/某项目（支持搜索）" />
          </el-form-item>
          <el-form-item label="启用打卡">
            <el-switch v-model="form.enable_clockin" active-text="开启自动任务" />
          </el-form-item>
        </el-tab-pane>

        <el-tab-pane label="打卡设置" name="clockin">
          <el-alert title="在地图上搜索或点击可自动获取经纬度和地址" type="info" :closable="false" style="margin-bottom: 15px;" />
          
          <el-form-item label="详细地址">
            <div class="place-row">
              <el-input
                class="place-input"
                v-model="searchQuery"
                placeholder="例如：四川省 · 成都市 · 高新区 · 科创十一街附近 / 天府广场"
                @keyup.enter="searchPlace"
              />
              <div class="place-actions">
                <el-button type="primary" @click="searchPlace">搜索</el-button>
                <el-button :disabled="!isEdit" :loading="addrFillLoading" @click="fillFromAccountAddress">账号地址填充</el-button>
              </div>
            </div>
          </el-form-item>

          <div id="map" class="map"></div>

          <el-form-item label="上班打卡">
            <el-time-select v-model="form.clockIn.schedule.startTime" start="00:00" step="00:01" end="23:59" />
          </el-form-item>
          <el-form-item label="下班打卡">
            <el-time-select v-model="form.clockIn.schedule.endTime" start="00:00" step="00:01" end="23:59" />
          </el-form-item>
          <el-form-item label="打卡周期">
            <el-checkbox-group v-model="form.clockIn.schedule.weekdays" class="week-group">
              <el-checkbox v-for="d in weekdayOptions" :key="d.value" :label="d.value">{{ d.label }}</el-checkbox>
            </el-checkbox-group>
          </el-form-item>
          <el-form-item label="打卡天数">
            <el-input-number v-model="form.clockIn.schedule.totalDays" :min="1" :max="3650" />
          </el-form-item>
          <el-row>
            <el-col :xs="24" :sm="12">
              <el-form-item label="纬度">
                <el-input v-model="form.clockIn.location.latitude" />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12">
              <el-form-item label="经度">
                <el-input v-model="form.clockIn.location.longitude" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row>
             <el-col :xs="24" :sm="8">
               <el-form-item label="省份">
                <el-input v-model="form.clockIn.location.province" />
              </el-form-item>
             </el-col>
             <el-col :xs="24" :sm="8">
               <el-form-item label="城市">
                <el-input v-model="form.clockIn.location.city" />
              </el-form-item>
             </el-col>
             <el-col :xs="24" :sm="8">
               <el-form-item label="区域">
                <el-input v-model="form.clockIn.location.area" />
              </el-form-item>
             </el-col>
          </el-row>
        </el-tab-pane>

        <el-tab-pane label="报告设置" name="report">
          <el-divider content-position="left">日报</el-divider>
          <el-form-item label="启用日报">
            <el-switch v-model="form.reportSettings.daily.enabled" />
          </el-form-item>
          <el-form-item v-if="form.reportSettings.daily.enabled" label="提交时间">
            <el-time-select v-model="form.reportSettings.daily.submitTime" start="00:00" step="00:01" end="23:59" />
          </el-form-item>
          <el-form-item v-if="form.reportSettings.daily.enabled" label="提交日(周)">
            <el-checkbox-group v-model="form.reportSettings.daily.submitDays" class="week-group">
              <el-checkbox v-for="d in weekdayOptions" :key="d.value" :label="d.value">{{ d.label }}</el-checkbox>
            </el-checkbox-group>
          </el-form-item>
          <el-form-item v-if="form.reportSettings.daily.enabled" label="日报预览">
            <div class="report-preview">
              <div class="report-preview-meta">字数：{{ dailyCount }} / 1000</div>
              <el-input v-model="reportPreview.daily" type="textarea" :rows="6" readonly resize="none" />
            </div>
          </el-form-item>
          
          <el-divider content-position="left">周报</el-divider>
          <el-form-item label="启用周报">
            <el-switch v-model="form.reportSettings.weekly.enabled" />
          </el-form-item>
          <el-form-item label="提交时间(周几)">
             <el-input-number v-model="form.reportSettings.weekly.submitTime" :min="1" :max="7" />
          </el-form-item>
          <el-form-item v-if="form.reportSettings.weekly.enabled" label="周报预览">
            <div class="report-preview">
              <div class="report-preview-meta">字数：{{ weeklyCount }} / 1000</div>
              <el-input v-model="reportPreview.weekly" type="textarea" :rows="6" readonly resize="none" />
            </div>
          </el-form-item>

           <el-divider content-position="left">月报</el-divider>
          <el-form-item label="启用月报">
            <el-switch v-model="form.reportSettings.monthly.enabled" />
          </el-form-item>
          <el-form-item label="提交时间(号)">
             <el-input-number v-model="form.reportSettings.monthly.submitTime" :min="1" :max="31" />
          </el-form-item>
          <el-form-item v-if="form.reportSettings.monthly.enabled" label="月报预览">
            <div class="report-preview">
              <div class="report-preview-meta">字数：{{ monthlyCount }} / 1000</div>
              <el-input v-model="reportPreview.monthly" type="textarea" :rows="6" readonly resize="none" />
            </div>
          </el-form-item>
        </el-tab-pane>
        
        <el-tab-pane label="AI 设置" name="ai">
             <el-form-item label="Model">
                <el-input v-model="form.ai.model" placeholder="gpt-4o-mini" />
             </el-form-item>
             <el-form-item label="API Key">
                <el-input v-model="form.ai.apikey" type="password" show-password :placeholder="secretPlaceholder" />
             </el-form-item>
              <el-form-item label="API URL">
                <el-input v-model="form.ai.apiUrl" placeholder="https://api.openai.com/ 或 https://api-inference.modelscope.cn/v1" />
             </el-form-item>
             <el-form-item label="测试">
                <div class="ai-test-row">
                  <el-button type="primary" :loading="aiTestLoading" @click="testAi">测试 AI</el-button>
                  <el-button @click="applyModelScopePreset">魔搭预设</el-button>
                  <el-tag v-if="aiTestStatus" size="small" :type="aiTestStatus === 'ok' ? 'success' : 'danger'">
                    {{ aiTestStatus === 'ok' ? '可用' : '不可用' }}
                  </el-tag>
                  <span v-if="aiTestLatencyMs !== null" class="ai-test-meta">延迟：{{ aiTestLatencyMs }}ms</span>
                </div>
             </el-form-item>
        </el-tab-pane>
      </el-tabs>

      <el-form-item v-if="!isMobile" class="desktop-actions">
        <div class="form-actions">
          <el-button type="primary" @click="save">保存</el-button>
          <el-button @click="$router.back()">取消</el-button>
        </div>
      </el-form-item>

      <div v-if="isMobile" class="mobile-actions-spacer"></div>
    </el-form>
  </el-card>

  <div v-if="isMobile" class="mobile-bottom-actions">
    <div class="mobile-bottom-actions-inner">
      <el-button type="primary" style="flex: 1" @click="save">保存</el-button>
      <el-button style="flex: 1" @click="$router.back()">取消</el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, computed, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { http } from '../api/http'
import { parseCnDotAddress, formatCnDotAddress } from '../utils/cnAddress'

import icon from 'leaflet/dist/images/marker-icon.png'
import iconShadow from 'leaflet/dist/images/marker-shadow.png'
let DefaultIcon = L.icon({
    iconUrl: icon,
    shadowUrl: iconShadow,
    iconSize: [25, 41],
    iconAnchor: [12, 41]
});
L.Marker.prototype.options.icon = DefaultIcon;

const route = useRoute()
const router = useRouter()
const isEdit = computed(() => !!route.params.id)
const passwordPlaceholder = computed(() => (isEdit.value ? '不修改请留空' : '请输入工学云密码'))
const secretPlaceholder = computed(() => (isEdit.value ? '不修改请留空' : ''))
const loading = ref(false)
const activeTab = ref('basic')
const mapInstance = ref(null)
const marker = ref(null)
const isMobile = ref(false)
const aiTestLoading = ref(false)
const aiTestStatus = ref('')
const aiTestLatencyMs = ref(null)
const addrFillLoading = ref(false)
const reportPreview = reactive({ daily: '', weekly: '', monthly: '' })

const _countText = (t) => {
  const s = String(t || '').replace(/\s+/g, '')
  return Math.min(1000, s.length)
}
const dailyCount = computed(() => _countText(reportPreview.daily))
const weeklyCount = computed(() => _countText(reportPreview.weekly))
const monthlyCount = computed(() => _countText(reportPreview.monthly))
const weekdayOptions = [
  { label: '周一', value: 1 },
  { label: '周二', value: 2 },
  { label: '周三', value: 3 },
  { label: '周四', value: 4 },
  { label: '周五', value: 5 },
  { label: '周六', value: 6 },
  { label: '周日', value: 7 },
]

const form = reactive({
  phone: '',
  password: '',
  remark: '',
  enable_clockin: true,
  clockIn: {
    mode: 'custom',
    location: {
      address: '', latitude: '', longitude: '', province: '', city: '', area: ''
    },
    imageCount: 0,
    description: [],
    specialClockIn: false,
    customDays: [],
    schedule: {
      startTime: '07:30',
      endTime: '18:00',
      weekdays: [1, 2, 3, 4, 5, 6, 7],
      totalDays: 180,
      startDate: ''
    }
  },
  reportSettings: {
    daily: { enabled: true, imageCount: 0, submitTime: '12:00', submitDays: [1, 2, 3, 4, 5, 6, 7] },
    weekly: { enabled: false, imageCount: 0, submitTime: 4 },
    monthly: { enabled: false, imageCount: 0, submitTime: 29 }
  },
  ai: {
      model: "gpt-4o-mini",
      apikey: "",
      apiUrl: "https://api.openai.com/"
  },
  pushNotifications: [],
  device: "{brand: TA J20, systemVersion: 17, Platform: Android, isPhysicalDevice: true, incremental: K23V10A}"
})

const searchQuery = computed({
  get: () => form.clockIn?.location?.address || '',
  set: (v) => {
    form.clockIn.location.address = String(v ?? '')
  },
})

const _cleanSegment = (v) => String(v || '').replace(/\s+/g, ' ').trim()

const _dedupeSegments = (segments) => {
  const out = []
  for (const s of segments) {
    const seg = _cleanSegment(s)
    if (!seg) continue
    if (out.length && out[out.length - 1] === seg) continue
    out.push(seg)
  }
  return out
}

const _composeAddress = (segments) => _dedupeSegments(segments).join(' · ')

const _pickFirst = (...vals) => {
  for (const v of vals) {
    const s = _cleanSegment(v)
    if (s) return s
  }
  return ''
}

const applyAddressStruct = (rawAddress, opts = {}) => {
  const input = String(rawAddress ?? '')
  const hasDot = /[·•]/.test(input)
  if (!hasDot && !opts?.force) return
  const parsed = parseCnDotAddress(input)
  if (parsed?.province) form.clockIn.location.province = parsed.province
  if (parsed?.province === '北京' || parsed?.province === '天津' || parsed?.province === '上海' || parsed?.province === '重庆') {
    form.clockIn.location.city = ''
  } else if (parsed?.city) {
    form.clockIn.location.city = parsed.city
  }
  if (parsed?.district) form.clockIn.location.area = parsed.district

  const rewriteAddress = typeof opts?.rewriteAddress === 'boolean' ? opts.rewriteAddress : hasDot
  if (rewriteAddress) {
    const normalized = formatCnDotAddress(parsed)
    if (normalized) form.clockIn.location.address = normalized
  }
}

const updateLocation = async (lat, lng, label = '') => {
    // 确保是数字
    lat = parseFloat(lat);
    lng = parseFloat(lng);

    // 更新 Marker
    if (marker.value) {
        marker.value.setLatLng([lat, lng]);
    } else {
        marker.value = L.marker([lat, lng]).addTo(mapInstance.value);
    }
    
    // 更新表单经纬度
    form.clockIn.location.latitude = lat.toFixed(6);
    form.clockIn.location.longitude = lng.toFixed(6);
    
    // 如果有搜索提供的地址标签，先预填
    if (label) {
        form.clockIn.location.address = _composeAddress(String(label).split(/[·,，]/g));
        applyAddressStruct(form.clockIn.location.address, { rewriteAddress: true })
    }
    
    // 逆地理编码获取地址信息
    try {
        const res = await http.get('/geocode/reverse', { params: { lat, lon: lng } })
        const payload = res.data?.result
        if (payload && payload.address) {
            const addr = payload.address;
            const province = _pickFirst(addr.province, addr.state, addr.region, addr.state_district)
            const city = _pickFirst(addr.city, addr.town, addr.municipality, addr.county, addr.state_district)
            const area = _pickFirst(addr.city_district, addr.district, addr.county, addr.suburb, addr.borough, addr.village)

            form.clockIn.location.province = province
            form.clockIn.location.city = city
            form.clockIn.location.area = area
            
            // 构造详细地址
            const fullAddr = _cleanSegment(payload.display_name)
            const place = _pickFirst(payload.name, fullAddr.split(',')[0])
            form.clockIn.location.address = _composeAddress([province, city, area, place])
            applyAddressStruct(form.clockIn.location.address, { rewriteAddress: true })
        }
    } catch (err) {
        console.error("逆地理编码失败", err);
        if (!label) {
             ElMessage.warning(err.response?.data?.detail || '无法自动获取详细地址，请手动填写');
        }
    }
}

const normalizeSearchQuery = (q) => {
  return String(q || '')
    .replace(/·/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

const searchPlace = async () => {
    const q = normalizeSearchQuery(searchQuery.value)
    if (!q) {
        ElMessage.warning('请输入要搜索的地点')
        return
    }
    if (!mapInstance.value) {
        return
    }
    try {
        const res = await http.get('/geocode/search', { params: { q } })
        const results = res.data?.results || []
        if (!Array.isArray(results) || results.length === 0) {
            ElMessage.warning('没有搜索到结果，请换一个关键词')
            return
        }
        const best = results[0]
        const lat = Number(best.y)
        const lng = Number(best.x)

        if (best.bounds && Array.isArray(best.bounds)) {
            mapInstance.value.fitBounds(best.bounds, { padding: [20, 20] })
        } else {
            mapInstance.value.setView([lat, lng], 16)
        }
        updateLocation(lat, lng, best.label || q)
    } catch (e) {
        ElMessage.error(e.response?.data?.detail || '搜索失败，请稍后再试')
    }
}

const initMap = () => {
  if (mapInstance.value) return;

  let lat = 30.5728;
  let lng = 104.0668;
  
  if (form.clockIn.location.latitude && form.clockIn.location.longitude) {
      lat = parseFloat(form.clockIn.location.latitude);
      lng = parseFloat(form.clockIn.location.longitude);
  }

  mapInstance.value = L.map('map').setView([lat, lng], 13);
  
  const tileProvider = String(import.meta.env.VITE_MAP_TILE_PROVIDER || '').trim().toLowerCase()
  const tdtKey = String(import.meta.env.VITE_TDT_KEY || '').trim()
  const useTdt = (tileProvider === 'tdt' || tileProvider === 'tianditu') || (!tileProvider && !!tdtKey)

  if (useTdt && tdtKey) {
    const subdomains = ['0', '1', '2', '3', '4', '5', '6', '7']
    L.tileLayer(`https://t{s}.tianditu.gov.cn/DataServer?T=vec_w&x={x}&y={y}&l={z}&tk=${encodeURIComponent(tdtKey)}`, {
      subdomains,
      maxZoom: 18,
      attribution: '© 天地图'
    }).addTo(mapInstance.value)
    L.tileLayer(`https://t{s}.tianditu.gov.cn/DataServer?T=cva_w&x={x}&y={y}&l={z}&tk=${encodeURIComponent(tdtKey)}`, {
      subdomains,
      maxZoom: 18,
      attribution: '© 天地图'
    }).addTo(mapInstance.value)
  } else {
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors'
    }).addTo(mapInstance.value)
  }

  if (form.clockIn.location.latitude && form.clockIn.location.longitude) {
      marker.value = L.marker([lat, lng]).addTo(mapInstance.value);
  }

  mapInstance.value.on('click', async (e) => {
      const { lat, lng } = e.latlng;
      updateLocation(lat, lng);
  });
}

const fetchUser = async () => {
  if (!isEdit.value) return
  loading.value = true
  try {
    const res = await http.get(`/users/${route.params.id}`)
    Object.assign(form, res.data)
    form.password = ''
    if (form.ai && typeof form.ai === 'object') {
      form.ai.apikey = ''
    }
    const last = res.data?.last_execution_result || []
    if (Array.isArray(last)) {
      reportPreview.daily = (last.find(i => i?.task_type === '日报提交' && i?.report_content)?.report_content) || ''
      reportPreview.weekly = (last.find(i => i?.task_type === '周报提交' && i?.report_content)?.report_content) || ''
      reportPreview.monthly = (last.find(i => i?.task_type === '月报提交' && i?.report_content)?.report_content) || ''
    }
    if (!form.clockIn) {
      form.clockIn = {}
    }
    if (!form.clockIn.schedule) {
      form.clockIn.schedule = { startTime: '07:30', endTime: '18:00', weekdays: [1,2,3,4,5,6,7], totalDays: 180, startDate: '' }
    } else {
      if (!form.clockIn.schedule.startTime) form.clockIn.schedule.startTime = '07:30'
      if (!form.clockIn.schedule.endTime) form.clockIn.schedule.endTime = '18:00'
      if (!Array.isArray(form.clockIn.schedule.weekdays)) {
        form.clockIn.schedule.weekdays = Array.isArray(form.clockIn.customDays) && form.clockIn.customDays.length ? form.clockIn.customDays : [1,2,3,4,5,6,7]
      }
      if (!form.clockIn.schedule.totalDays) form.clockIn.schedule.totalDays = 180
      if (!form.clockIn.schedule.startDate) form.clockIn.schedule.startDate = ''
    }
    if (!form.reportSettings) {
      form.reportSettings = { daily: {}, weekly: {}, monthly: {} }
    }
    if (!form.reportSettings.daily) {
      form.reportSettings.daily = { enabled: false, imageCount: 0, submitTime: '12:00', submitDays: [1, 2, 3, 4, 5, 6, 7] }
    } else {
      if (!form.reportSettings.daily.submitTime) form.reportSettings.daily.submitTime = '12:00'
      if (!Array.isArray(form.reportSettings.daily.submitDays)) {
        form.reportSettings.daily.submitDays = [1, 2, 3, 4, 5, 6, 7]
      }
    }
  } catch (error) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

const save = async () => {
  try {
    form.clockIn.mode = 'custom'
    form.clockIn.customDays = form.clockIn.schedule.weekdays
    const payload = JSON.parse(JSON.stringify(form))
    if (isEdit.value) {
      if (!String(payload.password || '').trim()) delete payload.password
      if (payload.ai && typeof payload.ai === 'object') {
        if (!String(payload.ai.apikey || '').trim()) delete payload.ai.apikey
      }
    }
    if (isEdit.value) {
      await http.patch(`/users/${route.params.id}`, payload)
    } else {
      await http.post('/users', payload)
    }
    ElMessage.success('保存成功')
    router.push('/')
  } catch (error) {
    ElMessage.error('保存失败: ' + (error.friendlyMessage || error.message))
  }
}

const testAi = async () => {
  const apiUrl = (form.ai.apiUrl || '').trim()
  const apikey = (form.ai.apikey || '').trim()
  const model = (form.ai.model || '').trim()
  if (!apiUrl || !apikey || !model) {
    ElMessage.warning('请先填写 API URL、API Key 和 Model')
    return
  }
  aiTestLoading.value = true
  aiTestStatus.value = ''
  aiTestLatencyMs.value = null
  try {
    const res = await http.post('/ai/test', { apiUrl, apikey, model })
    aiTestStatus.value = res.data?.ok ? 'ok' : 'fail'
    aiTestLatencyMs.value = typeof res.data?.latency_ms === 'number' ? res.data.latency_ms : null
    ElMessage.success('AI 可用')
  } catch (e) {
    aiTestStatus.value = 'fail'
    ElMessage.error(e.friendlyMessage || e.response?.data?.detail || 'AI 测试失败')
  } finally {
    aiTestLoading.value = false
  }
}

const applyModelScopePreset = () => {
  form.ai.apiUrl = 'https://api-inference.modelscope.cn/v1'
  form.ai.model = 'Qwen/Qwen3-Next-80B-A3B-Instruct'
  aiTestStatus.value = ''
  aiTestLatencyMs.value = null
  ElMessage.success('已填入魔搭预设，请粘贴 Token 后点击“测试 AI”')
}

const _pickBestAddress = (...values) => {
  const list = []
  for (const v of values.flat(2)) {
    const s = String(v || '').trim()
    if (s) list.push(s)
  }
  if (!list.length) return ''
  const unique = []
  for (const s of list) {
    if (!unique.includes(s)) unique.push(s)
  }
  unique.sort((x, y) => y.length - x.length)
  return unique[0] || ''
}

const fillFromAccountAddress = async () => {
  if (!isEdit.value) {
    ElMessage.warning('请先保存用户后再自动填充')
    return
  }
  addrFillLoading.value = true
  try {
    const res = await http.get(`/users/${route.params.id}/account-address`)
    const bestAddr = _pickBestAddress(res.data?.address, res.data?.addressCandidates)
    if (!bestAddr) {
      ElMessage.warning('未获取到账号详细地址')
      return
    }
    form.clockIn.location.address = bestAddr
    searchQuery.value = bestAddr
    if (!mapInstance.value) {
      initMap()
      await nextTick()
    }
    await searchPlace()
    ElMessage.success('已填入账号详细地址，并尝试自动定位经纬度')
  } catch (e) {
    ElMessage.error(e.friendlyMessage || e.response?.data?.detail || '自动填充失败')
  } finally {
    addrFillLoading.value = false
  }
}

// 监听 Tab 切换，初始化地图
watch(activeTab, (val) => {
    if (val === 'clockin') {
        nextTick(() => {
            initMap();
            setTimeout(() => {
                mapInstance.value?.invalidateSize();
            }, 100);
        });
    }
});

onMounted(async () => {
    await fetchUser();
    if (activeTab.value === 'clockin') {
        initMap();
    }
})

let addrStructTimer = null
watch(
  () => form.clockIn?.location?.address,
  (val) => {
    const s = String(val || '').trim()
    if (!s) return
    if (!/[·•]/.test(s)) return
    if (addrStructTimer) clearTimeout(addrStructTimer)
    addrStructTimer = setTimeout(() => {
      applyAddressStruct(s)
    }, 350)
  }
)

const updateIsMobile = () => {
  isMobile.value = window.matchMedia('(max-width: 768px)').matches
}

onMounted(() => {
  updateIsMobile()
  window.addEventListener('resize', updateIsMobile)
})
onUnmounted(() => {
  if (addrStructTimer) clearTimeout(addrStructTimer)
  window.removeEventListener('resize', updateIsMobile)
})
</script>

<style scoped>
.desktop-actions {
  margin-top: 20px;
}
.map {
  height: 300px;
  margin-bottom: 20px;
  border-radius: 4px;
  border: 1px solid var(--el-border-color);
  z-index: 1;
}
.place-row {
  display: flex;
  gap: 10px;
  width: 100%;
}
.place-input {
  flex: 1;
  min-width: 0;
}
.place-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.place-actions :deep(.el-button) {
  white-space: nowrap;
}
.week-group {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.form-actions {
  display: flex;
  gap: 12px;
}
.mobile-actions-spacer {
  height: calc(68px + env(safe-area-inset-bottom));
}
.mobile-bottom-actions {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  border-top: 1px solid var(--el-border-color);
  background-color: var(--el-bg-color);
  padding: 10px calc(12px + env(safe-area-inset-left)) calc(10px + env(safe-area-inset-bottom)) calc(12px + env(safe-area-inset-right));
  z-index: 1500;
}
.mobile-bottom-actions-inner {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  gap: 12px;
}
.ai-test-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.ai-test-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.report-preview {
  width: 100%;
}
.report-preview-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}
@media (max-width: 768px) {
  .map {
    height: 240px;
    margin-bottom: 16px;
  }
  .place-actions {
    margin-top: 8px;
  }
  .place-row {
    flex-direction: column;
  }
  .place-actions {
    width: 100%;
    justify-content: stretch;
  }
  .place-actions :deep(.el-button) {
    flex: 1;
  }
}
</style>
