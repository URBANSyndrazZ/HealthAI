<script setup lang="ts">
import { useRouter } from 'vue-router'
import { logout, useAuthState } from '@/api/auth'

const router = useRouter()
const { loggedIn, username } = useAuthState()

function handleLogout() {
  logout()
  router.push('/login')
}
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="brand">
        <img class="brand-logo" src="/health-logo.svg" alt="AI健康助手" />
        <div class="brand-copy">
          <strong>AI健康助手</strong>
          <span>更懂你的日常健康节律</span>
        </div>
      </div>

      <nav class="app-nav">
        <router-link to="/">智能对话</router-link>
        <router-link to="/health">健康档案</router-link>
        <router-link to="/import">数据导入</router-link>
        <router-link to="/profile">个人设置</router-link>
      </nav>

      <div class="auth-box">
        <span v-if="loggedIn">{{ username }}</span>
        <button v-if="loggedIn" @click="handleLogout">退出</button>
        <router-link v-else to="/login">登录</router-link>
      </div>
    </header>

    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html,
body,
#app {
  width: 100%;
  min-height: 100vh;
}

body {
  font-family:
    'PingFang SC',
    'Hiragino Sans GB',
    'Microsoft YaHei',
    'Segoe UI',
    sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background:
    radial-gradient(circle at top left, rgba(22, 119, 255, 0.14), transparent 32%),
    linear-gradient(180deg, #f4f9ff 0%, #eef5ff 100%);
  color: var(--text-primary);
}

#app {
  overflow: hidden;
}

.app-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-header {
  position: sticky;
  top: 0;
  z-index: 30;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 18px 32px;
  background: rgba(248, 252, 255, 0.88);
  border-bottom: 1px solid rgba(22, 119, 255, 0.12);
  backdrop-filter: blur(18px);
}

.brand {
  display: flex;
  align-items: center;
  gap: 14px;
}

.brand-logo {
  width: 44px;
  height: 44px;
  border-radius: 14px;
  box-shadow: 0 12px 24px rgba(22, 119, 255, 0.2);
}

.brand-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.brand-copy strong {
  font-size: 18px;
  color: var(--text-primary);
}

.brand-copy span {
  font-size: 12px;
  color: var(--text-secondary);
}

.app-nav {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.auth-box {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-secondary);
  font-size: 14px;
}

.auth-box button,
.auth-box a {
  border: 0;
  border-radius: 999px;
  padding: 9px 14px;
  background: rgba(22, 119, 255, 0.08);
  color: var(--brand-primary);
  text-decoration: none;
  font-weight: 600;
  cursor: pointer;
}

.app-nav a {
  padding: 10px 16px;
  border-radius: 999px;
  color: var(--text-secondary);
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  transition:
    background-color 0.2s ease,
    color 0.2s ease,
    box-shadow 0.2s ease;
}

.app-nav a:hover,
.app-nav a.router-link-active {
  color: var(--brand-primary);
  background: rgba(22, 119, 255, 0.08);
  box-shadow: inset 0 0 0 1px rgba(22, 119, 255, 0.12);
}

.app-main {
  flex: 1;
  min-height: 0;
}

::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: rgba(22, 119, 255, 0.24);
  border-radius: 999px;
}

::-webkit-scrollbar-thumb:hover {
  background: rgba(22, 119, 255, 0.4);
}

@media (max-width: 960px) {
  .app-header {
    padding: 16px 18px;
    flex-direction: column;
    align-items: flex-start;
  }

  .app-nav {
    width: 100%;
    overflow-x: auto;
    padding-bottom: 4px;
  }

  .app-nav a {
    white-space: nowrap;
  }
}
</style>
