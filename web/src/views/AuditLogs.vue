<template>
  <el-card class="page-card">
    <template #header>
      <div class="page-header">
        <div class="page-title">审计日志</div>
        <div class="page-actions">
          <el-input
            v-model="query"
            placeholder="搜索操作者/动作"
            clearable
            @keyup.enter="onSearch"
          />
          <el-button @click="onSearch">搜索</el-button>
          <el-button @click="resetSearch">重置</el-button>
        </div>
      </div>
    </template>

    <div class="table-wrap">
      <el-table :data="items" style="width: 100%" v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="created_at" label="时间" width="180" />
        <el-table-column prop="actor" label="操作者" width="140" />
        <el-table-column prop="action" label="动作" min-width="180" />
        <el-table-column prop="target_user_id" label="目标用户ID" width="120" />
        <el-table-column label="详情" min-width="240">
          <template #default="scope">
            <pre class="detail">{{ stringify(scope.row.detail) }}</pre>
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
        @size-change="fetchLogs"
        @current-change="fetchLogs"
      />
    </div>
  </el-card>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { http } from '../api/http'

const items = ref([])
const loading = ref(false)
const query = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

const stringify = (v) => {
  try {
    return JSON.stringify(v ?? {}, null, 0)
  } catch {
    return String(v ?? '')
  }
}

const fetchLogs = async () => {
  loading.value = true
  try {
    const res = await http.get('/audit-logs/page', {
      params: {
        page: page.value,
        pageSize: pageSize.value,
        q: query.value?.trim() || undefined,
      },
    })
    items.value = res.data.items || []
    total.value = res.data.total || 0
  } catch (e) {
    ElMessage.error(e.friendlyMessage || '获取审计日志失败')
  } finally {
    loading.value = false
  }
}

const onSearch = () => {
  page.value = 1
  fetchLogs()
}

const resetSearch = () => {
  query.value = ''
  page.value = 1
  fetchLogs()
}

onMounted(fetchLogs)
</script>

<style scoped>
.pager {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
}
.detail {
  margin: 0;
  white-space: pre-wrap;
  font-family: inherit;
  font-size: 12px;
  color: var(--el-text-color-regular);
  padding: 8px 10px;
  border-radius: 8px;
  background-color: var(--el-fill-color-light);
  max-height: 220px;
  overflow: auto;
}
</style>
