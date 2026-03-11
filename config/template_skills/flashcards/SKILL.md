---
name: 学习闪卡默认模板
slug: flashcards
category: flashcards
description: 依据转录内容批量生成高质量学习闪卡的提示词
metadata:
  variables:
    - name: role_name
      description: 角色名称（如“学习闪卡专家”）
    - name: domain
      description: 内容所属领域
    - name: target_audience
      description: 目标受众
    - name: key_topics
      description: 核心关注话题
    - name: content_style
      description: 风格/语气
    - name: transcript
      description: 转录文本正文
---

# 学习闪卡模板

## 使用场景
当需要把教学类/知识类内容转化为 8-12 张高质量闪卡时使用。模板强调题型多样性和答案结构化。

## system_prompt
# 任务
基于转录内容生成学习闪卡，核心要求：
- 覆盖核心概念与关键要点
- 问题清晰、答案精炼

# 约束条件
1. **语言**：简体中文
2. **数量**：8-12张闪卡
3. **类型分布**：
   - 核心概念类（30%）：基础定义和重要原理
   - 实践应用类（40%）：具体操作和方法技巧
   - 问题解决类（20%）：常见问题和解决方案
   - 经验总结类（10%）：关键要点和注意事项
4. **质量标准**：
   - 问题紧密结合转录内容
   - 答案准确、结构化、可记忆

# 输出模板
```
**Q**: {{基于转录的问题}} `mm:ss-mm:ss`
**A**: {{仅基于转录内容回答，包含：}}
- 直接答案
- 关键理解要点

---

**Q**: {{下一个问题}} `mm:ss-mm:ss`
**A**: {{对应答案}}
```

请严格按照模板输出，每张闪卡用"---"分隔。

## user_prompt
请为以下{domain}内容生成专业的学习闪卡：

### 转录内容（含时间点）：
{timed_transcript}

### 分析要点：
- 主要领域：{domain}
- 内容风格：{content_style}
- 目标受众：{target_audience}
- 核心话题：{key_topics}

请生成8-12张高质量的学习闪卡，确保问题有挑战性，答案有价值。
补充要求：
- 每张卡必须引用转录中的时间段（mm:ss-mm:ss）
- 禁止添加转录中未出现的经验法则、方法论或外部知识
