<template>
  <div class="profile-view">
    <section class="profile-card">
      <div class="profile-header">
        <img src="/health-logo.svg" alt="AI健康助手" class="avatar-logo" />
        <div>
          <span class="profile-badge">个人设置</span>
          <h1>让 AI健康助手更了解你的健康偏好</h1>
          <p>后续可在这里管理基础信息、健康目标、提醒方式和数据授权范围。</p>
        </div>
      </div>

      <div class="setting-grid">
        <article class="setting-item">
          <h2>健康目标</h2>
          <p>设置步数、睡眠和体重目标，生成更贴合你的长期建议。</p>
        </article>

        <article class="setting-item">
          <h2>偏好与提醒</h2>
          <p>定义作息偏好、饮食禁忌和通知频率，减少泛化建议。</p>
        </article>

        <article class="setting-item">
          <h2>隐私与授权</h2>
          <p>管理导入数据的使用范围，确保分析过程清晰可控。</p>
        </article>
      </div>

      <router-link to="/" class="back-link">返回智能对话</router-link>
    </section>
  </div>
</template>

<style scoped>
.profile-view {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px;
}

.profile-card {
  padding: 28px;
  border-radius: 30px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(245, 250, 255, 0.92));
  border: 1px solid rgba(22, 119, 255, 0.14);
  box-shadow: var(--shadow-card);
}

.profile-header {
  display: flex;
  align-items: flex-start;
  gap: 20px;
  margin-bottom: 26px;
}

.avatar-logo {
  width: 88px;
  height: 88px;
  flex-shrink: 0;
}

.profile-badge {
  display: inline-flex;
  margin-bottom: 12px;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(22, 119, 255, 0.08);
  color: var(--brand-primary);
  font-size: 12px;
  font-weight: 600;
}

.profile-header h1 {
  margin-bottom: 10px;
  font-size: 30px;
  line-height: 1.25;
  color: var(--text-primary);
}

.profile-header p {
  color: var(--text-secondary);
  max-width: 680px;
}

.setting-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.setting-item {
  padding: 22px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.86);
  border: 1px solid rgba(22, 119, 255, 0.1);
}

.setting-item h2 {
  margin-bottom: 10px;
  font-size: 18px;
  color: var(--text-primary);
}

.setting-item p {
  color: var(--text-secondary);
  font-size: 14px;
}

.back-link {
  display: inline-flex;
  margin-top: 24px;
  color: var(--brand-primary);
  text-decoration: none;
  font-weight: 600;
}

@media (max-width: 860px) {
  .profile-view {
    padding: 16px;
  }

  .profile-header {
    flex-direction: column;
  }

  .setting-grid {
    grid-template-columns: 1fr;
  }
}
</style>
