<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { login, register } from '@/api/auth'

const router = useRouter()
const mode = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const loading = ref(false)

async function submit() {
  const normalizedUsername = username.value.trim()
  if (!normalizedUsername || !password.value) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  if (normalizedUsername.length < 3) {
    ElMessage.warning('用户名至少 3 位')
    return
  }
  if (password.value.length < 6) {
    ElMessage.warning('密码至少 6 位')
    return
  }

  loading.value = true
  try {
    if (mode.value === 'login') {
      await login({ username: normalizedUsername, password: password.value })
      ElMessage.success('登录成功')
    } else {
      await register({ username: normalizedUsername, password: password.value })
      ElMessage.success('注册成功')
    }
    const redirect = typeof router.currentRoute.value.query.redirect === 'string'
      ? router.currentRoute.value.query.redirect
      : '/'
    await router.push(redirect)
  } catch (error: any) {
    ElMessage.error(error.message || '操作失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-view">
    <section class="login-panel">
      <div class="brand-block">
        <img src="/health-logo.svg" alt="AI健康助手" />
        <div>
          <span>AI健康助手</span>
          <h1>{{ mode === 'login' ? '登录健康助手' : '创建健康助手账号' }}</h1>
        </div>
      </div>

      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="用户名">
          <el-input v-model="username" autocomplete="username" placeholder="至少 3 位" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="password"
            type="password"
            autocomplete="current-password"
            placeholder="至少 6 位"
            show-password
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button type="primary" size="large" :loading="loading" class="submit-btn" @click="submit">
          {{ mode === 'login' ? '登录' : '注册并登录' }}
        </el-button>
      </el-form>

      <button class="mode-btn" @click="mode = mode === 'login' ? 'register' : 'login'">
        {{ mode === 'login' ? '没有账号？去注册' : '已有账号？去登录' }}
      </button>
    </section>
  </div>
</template>

<style scoped>
.login-view {
  min-height: calc(100vh - 86px);
  display: grid;
  place-items: center;
  padding: 24px;
}

.login-panel {
  width: min(440px, 100%);
  padding: 30px;
  border: 1px solid var(--border-soft);
  border-radius: 24px;
  background: var(--surface-primary);
  box-shadow: var(--shadow-card);
}

.brand-block {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-bottom: 26px;
}

.brand-block img {
  width: 58px;
  height: 58px;
}

.brand-block span {
  color: var(--brand-primary);
  font-size: 13px;
  font-weight: 700;
}

.brand-block h1 {
  margin-top: 4px;
  font-size: 26px;
  color: var(--text-primary);
}

.submit-btn {
  width: 100%;
  margin-top: 6px;
}

.mode-btn {
  width: 100%;
  margin-top: 18px;
  border: 0;
  background: transparent;
  color: var(--brand-primary);
  font-weight: 600;
  cursor: pointer;
}
</style>
