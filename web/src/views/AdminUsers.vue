<template>
  <el-card class="page-card">
    <template #header>
      <div class="page-header">
        <div class="page-title">账号管理</div>
        <div class="page-actions">
          <el-input
            v-model="query"
            placeholder="搜索用户名"
            clearable
            @keyup.enter="onSearch"
          />
          <el-button @click="onSearch">搜索</el-button>
          <el-button @click="resetSearch">重置</el-button>
          <el-button type="primary" @click="openCreate">新增账号</el-button>
        </div>
      </div>
    </template>

    <div class="table-wrap">
      <el-table :data="items" style="width: 100%" v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column prop="username" label="用户名" width="160" />
        <el-table-column label="角色" width="140">
          <template #default="scope">
            <el-select v-model="scope.row.role" size="small" style="width: 120px" @change="onRoleChange(scope.row)">
              <el-option label="管理员" value="admin" />
              <el-option label="操作员" value="operator" />
              <el-option label="只读" value="viewer" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="120">
          <template #default="scope">
            <el-switch v-model="scope.row.enabled" @change="onEnabledChange(scope.row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="200">
          <template #default="scope">
            <el-button size="small" type="warning" @click="openResetPassword(scope.row)">重置密码</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="pager">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50, 100, 200]"
        :total="total"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="fetchUsers"
        @current-change="fetchUsers"
      />
    </div>

    <el-dialog v-model="createVisible" title="新增账号" :width="isMobile ? '92%' : '520px'">
      <el-form :model="createForm" label-width="90px">
        <el-form-item label="用户名">
          <el-input v-model="createForm.username" placeholder="例如：admin2" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="createForm.password" type="password" show-password placeholder="至少6位" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="createForm.role" style="width: 100%">
            <el-option label="管理员" value="admin" />
            <el-option label="操作员" value="operator" />
            <el-option label="只读" value="viewer" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="createVisible = false">取消</el-button>
          <el-button type="primary" :loading="createLoading" @click="createUser">创建</el-button>
        </span>
      </template>
    </el-dialog>

    <el-dialog v-model="resetVisible" title="重置密码" :width="isMobile ? '92%' : '520px'">
      <el-form :model="resetForm" label-width="90px">
        <el-form-item label="用户名">
          <el-input v-model="resetForm.username" disabled />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="resetForm.password" type="password" show-password placeholder="至少6位" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="resetVisible = false">取消</el-button>
          <el-button type="primary" :loading="resetLoading" @click="resetPassword">保存</el-button>
        </span>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { http } from '../api/http'

const items = ref([])
const loading = ref(false)
const isMobile = ref(false)
const query = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
let removeMqListener = null

const createVisible = ref(false)
const createLoading = ref(false)
const createForm = reactive({ username: '', password: '', role: 'viewer' })

const resetVisible = ref(false)
const resetLoading = ref(false)
const resetForm = reactive({ id: null, username: '', password: '' })

const fetchUsers = async () => {
  loading.value = true
  try {
    const res = await http.get('/admin-users/page', {
      params: {
        page: page.value,
        pageSize: pageSize.value,
        q: query.value?.trim() || undefined,
      },
    })
    items.value = res.data.items || []
    total.value = res.data.total || 0
  } catch (e) {
    ElMessage.error(e.friendlyMessage || '获取账号列表失败')
  } finally {
    loading.value = false
  }
}

const onSearch = () => {
  page.value = 1
  fetchUsers()
}

const resetSearch = () => {
  query.value = ''
  page.value = 1
  fetchUsers()
}

const openCreate = () => {
  createForm.username = ''
  createForm.password = ''
  createForm.role = 'viewer'
  createVisible.value = true
}

const createUser = async () => {
  createLoading.value = true
  try {
    await http.post('/admin-users', {
      username: createForm.username?.trim(),
      password: createForm.password?.trim(),
      role: createForm.role,
    })
    ElMessage.success('创建成功')
    createVisible.value = false
    fetchUsers()
  } catch (e) {
    ElMessage.error(e.friendlyMessage || '创建失败')
  } finally {
    createLoading.value = false
  }
}

const onRoleChange = async (row) => {
  try {
    await http.patch(`/admin-users/${row.id}`, { role: row.role })
    ElMessage.success('已更新角色')
  } catch (e) {
    ElMessage.error(e.friendlyMessage || '更新失败')
    fetchUsers()
  }
}

const onEnabledChange = async (row) => {
  try {
    await http.patch(`/admin-users/${row.id}`, { enabled: row.enabled })
    ElMessage.success('已更新状态')
  } catch (e) {
    ElMessage.error(e.friendlyMessage || '更新失败')
    fetchUsers()
  }
}

const openResetPassword = (row) => {
  resetForm.id = row.id
  resetForm.username = row.username
  resetForm.password = ''
  resetVisible.value = true
}

const resetPassword = async () => {
  if (!resetForm.id) return
  resetLoading.value = true
  try {
    await http.post(`/admin-users/${resetForm.id}/reset-password`, {
      password: resetForm.password?.trim(),
    })
    ElMessage.success('密码已重置')
    resetVisible.value = false
  } catch (e) {
    ElMessage.error(e.friendlyMessage || '重置失败')
  } finally {
    resetLoading.value = false
  }
}

onMounted(fetchUsers)
onMounted(() => {
  const mq = window.matchMedia?.('(max-width: 768px)')
  const update = () => (isMobile.value = !!mq?.matches)
  update()
  mq?.addEventListener?.('change', update)
  removeMqListener = () => mq?.removeEventListener?.('change', update)
})
onUnmounted(() => removeMqListener?.())
</script>

<style scoped>
.pager {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
}
</style>

