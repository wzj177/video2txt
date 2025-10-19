#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI内容分析器 - 智能识别内容领域并生成动态提示词
实现内容分析→领域识别→动态提示词生成的完整流程
"""

import logging
import json
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ContentDomain(Enum):
    """内容领域枚举"""

    EDUCATION = "education"  # 教育学习
    EXAM_REVIEW = "exam_review"  # 试卷评讲
    MEETING = "meeting"  # 会议纪要
    TRAVEL = "travel"  # 旅游探索
    COOKING = "cooking"  # 烹饪美食
    LIFESTYLE = "lifestyle"  # 生活方式
    TECHNOLOGY = "technology"  # 科技数码
    BUSINESS = "business"  # 商业财经
    HEALTH = "health"  # 健康养生
    ENTERTAINMENT = "entertainment"  # 娱乐休闲
    NEWS = "news"  # 新闻资讯
    SPORTS = "sports"  # 体育运动
    GENERAL = "general"  # 通用内容


@dataclass
class ContentAnalysisResult:
    """内容分析结果"""

    primary_domain: ContentDomain
    secondary_domains: List[ContentDomain]
    confidence: float
    key_topics: List[str]
    content_style: str  # 讲解式、对话式、演示式等
    target_audience: str  # 初学者、进阶者、专业人士等
    content_length: str  # 短、中、长
    visual_elements: List[str]  # 图表、演示、实物等


class AIContentAnalyzer:
    """AI内容分析器 - 智能分析内容并生成动态提示词"""

    def __init__(self, ai_client):
        self.ai_client = ai_client
        self.domain_keywords = self._initialize_domain_keywords()
        logger.info("🧠 AI内容分析器初始化完成")

    def _initialize_domain_keywords(self) -> Dict[ContentDomain, List[str]]:
        """初始化领域关键词映射"""
        return {
            ContentDomain.EDUCATION: [
                "教学",
                "学习",
                "课程",
                "知识",
                "原理",
                "方法",
                "步骤",
                "技巧",
                "概念",
                "理论",
                "实践",
                "练习",
                "考试",
                "培训",
                "教育",
                "讲解",
                "分析",
                "总结",
            ],
            ContentDomain.EXAM_REVIEW: [
                "试卷",
                "题目",
                "答案",
                "解析",
                "评讲",
                "选择题",
                "填空题",
                "解答题",
                "应用题",
                "证明题",
                "计算题",
                "分析题",
                "错误",
                "正确",
                "得分",
                "失分",
                "考点",
                "知识点",
                "解题",
                "思路",
                "方法",
                "技巧",
                "注意",
                "易错",
                "难点",
                "重点",
                "公式",
                "定理",
                "概念",
                "原理",
                "步骤",
                "过程",
                "结果",
                "检查",
                "验证",
                "总结",
                "归纳",
            ],
            ContentDomain.MEETING: [
                "会议",
                "讨论",
                "决议",
                "议题",
                "汇报",
                "总结",
                "计划",
                "方案",
                "建议",
                "意见",
                "反馈",
                "问题",
                "解决",
                "安排",
                "分工",
                "责任",
                "进度",
                "时间",
                "预算",
                "资源",
                "目标",
                "成果",
                "评估",
                "跟进",
                "行动",
                "执行",
                "协调",
                "沟通",
                "确认",
                "批准",
                "通过",
                "否决",
                "推迟",
                "调整",
                "优化",
                "改进",
                "风险",
                "机会",
                "挑战",
                "策略",
                "战略",
                "战术",
                "部门",
                "团队",
                "人员",
                "领导",
                "管理",
                "监督",
                "检查",
                "审核",
                "验收",
            ],
            ContentDomain.TRAVEL: [
                "旅游",
                "旅行",
                "景点",
                "攻略",
                "路线",
                "酒店",
                "美景",
                "文化",
                "风俗",
                "地方",
                "城市",
                "国家",
                "探索",
                "体验",
                "游记",
                "推荐",
                "打卡",
            ],
            ContentDomain.COOKING: [
                "做饭",
                "烹饪",
                "菜谱",
                "食材",
                "调料",
                "口味",
                "营养",
                "制作",
                "步骤",
                "技巧",
                "美食",
                "料理",
                "食谱",
                "厨艺",
                "味道",
                "健康",
                "搭配",
            ],
            ContentDomain.LIFESTYLE: [
                "生活",
                "日常",
                "习惯",
                "品质",
                "家居",
                "装修",
                "搭配",
                "时尚",
                "购物",
                "分享",
                "体验",
                "感受",
                "心得",
                "建议",
                "推荐",
                "实用",
                "便民",
            ],
            ContentDomain.TECHNOLOGY: [
                "科技",
                "技术",
                "数码",
                "软件",
                "硬件",
                "编程",
                "开发",
                "AI",
                "人工智能",
                "互联网",
                "应用",
                "功能",
                "操作",
                "设置",
                "评测",
                "新品",
                "创新",
            ],
            ContentDomain.BUSINESS: [
                "商业",
                "生意",
                "创业",
                "投资",
                "理财",
                "经济",
                "市场",
                "营销",
                "管理",
                "策略",
                "分析",
                "趋势",
                "机会",
                "风险",
                "收益",
                "成本",
                "效率",
            ],
            ContentDomain.HEALTH: [
                "健康",
                "养生",
                "运动",
                "锻炼",
                "饮食",
                "营养",
                "医疗",
                "保健",
                "康复",
                "预防",
                "治疗",
                "身体",
                "心理",
                "疾病",
                "症状",
                "建议",
                "方法",
            ],
            ContentDomain.ENTERTAINMENT: [
                "娱乐",
                "电影",
                "音乐",
                "游戏",
                "综艺",
                "明星",
                "八卦",
                "搞笑",
                "有趣",
                "好玩",
                "精彩",
                "刺激",
                "放松",
                "休闲",
                "消遣",
                "评论",
                "推荐",
            ],
            ContentDomain.NEWS: [
                "新闻",
                "资讯",
                "时事",
                "政治",
                "社会",
                "国际",
                "国内",
                "事件",
                "报道",
                "分析",
                "评论",
                "观点",
                "影响",
                "发展",
                "变化",
                "趋势",
                "热点",
            ],
            ContentDomain.SPORTS: [
                "体育",
                "运动",
                "比赛",
                "训练",
                "健身",
                "球类",
                "竞技",
                "技巧",
                "战术",
                "成绩",
                "记录",
                "冠军",
                "团队",
                "个人",
                "精神",
                "坚持",
                "突破",
            ],
        }

    async def analyze_content(self, transcript: str, **kwargs) -> ContentAnalysisResult:
        """
        分析转录内容，识别领域和特征

        Args:
            transcript: 转录文本
            **kwargs: 额外参数（如视频时长、帧数等）

        Returns:
            ContentAnalysisResult: 分析结果
        """
        try:
            # 🎯 检查是否强制指定领域
            force_domain = kwargs.get("force_domain")
            if force_domain and force_domain != "auto":
                logger.info(f"🎯 强制使用指定领域: {force_domain}")

                # 验证并转换领域
                try:
                    forced_domain = ContentDomain(force_domain.lower())
                except ValueError:
                    # 如果不是有效的枚举值，尝试映射
                    domain_mapping = {
                        "meeting": ContentDomain.MEETING,
                        "education": ContentDomain.EDUCATION,
                        "exam_review": ContentDomain.EXAM_REVIEW,
                        "cooking": ContentDomain.COOKING,
                        "travel": ContentDomain.TRAVEL,
                        "technology": ContentDomain.TECHNOLOGY,
                        "business": ContentDomain.BUSINESS,
                        "health": ContentDomain.HEALTH,
                        "lifestyle": ContentDomain.LIFESTYLE,
                        "entertainment": ContentDomain.ENTERTAINMENT,
                    }
                    forced_domain = domain_mapping.get(
                        force_domain, ContentDomain.GENERAL
                    )

                # 进行基础分析（用于获取关键话题等）
                basic_analysis = await self._basic_content_analysis(transcript)
                content_features = await self._analyze_content_features(
                    transcript, **kwargs
                )

                # 🛡️ 防御性编程：确保分析结果不为None
                if basic_analysis is None:
                    basic_analysis = {
                        "main_theme": "未知主题",
                        "key_topics": [],
                        "content_summary": "内容分析失败",
                        "language_style": "通俗",
                        "emotional_tone": "中性",
                    }

                if content_features is None:
                    content_features = {
                        "content_style": "通俗",
                        "target_audience": "一般用户",
                        "content_length": "中等",
                        "visual_elements": "无",
                    }

                # 返回强制指定领域的结果
                result = ContentAnalysisResult(
                    primary_domain=forced_domain,
                    secondary_domains=[],
                    confidence=1.0,  # 强制指定的置信度为100%
                    key_topics=basic_analysis.get("key_topics", []),
                    content_style=content_features.get("content_style", "通俗"),
                    target_audience=content_features.get("target_audience", "一般用户"),
                    content_length=content_features.get("content_length", "中等"),
                    visual_elements=content_features.get("visual_elements", "无"),
                )

                logger.info(f" 强制使用{forced_domain.value}领域，置信度: 1.0")
                return result

            # 正常的智能分析流程
            # 1. 基础分析
            basic_analysis = await self._basic_content_analysis(transcript)

            # 🛡️ 防御性编程：确保基础分析结果不为None
            if basic_analysis is None:
                basic_analysis = {
                    "main_theme": "未知主题",
                    "key_topics": [],
                    "content_summary": "内容分析失败",
                    "language_style": "通俗",
                    "emotional_tone": "中性",
                }

            # 2. 领域识别
            domain_analysis = await self._domain_classification(
                transcript, basic_analysis
            )

            # 🛡️ 防御性编程：确保领域分析结果不为None
            if domain_analysis is None:
                domain_analysis = {
                    "primary_domain": ContentDomain.GENERAL,
                    "secondary_domains": [],
                    "confidence": 0.5,
                }

            # 3. 内容特征分析
            content_features = await self._analyze_content_features(
                transcript, **kwargs
            )

            # 🛡️ 防御性编程：确保内容特征分析结果不为None
            if content_features is None:
                content_features = {
                    "content_style": "通俗",
                    "target_audience": "一般用户",
                    "content_length": "中等",
                    "visual_elements": "无",
                }

            # 4. 综合分析结果
            result = ContentAnalysisResult(
                primary_domain=domain_analysis.get(
                    "primary_domain", ContentDomain.GENERAL
                ),
                secondary_domains=domain_analysis.get("secondary_domains", []),
                confidence=domain_analysis.get("confidence", 0.5),
                key_topics=basic_analysis.get("key_topics", []),
                content_style=content_features.get("content_style", "通俗"),
                target_audience=content_features.get("target_audience", "一般用户"),
                content_length=content_features.get("content_length", "中等"),
                visual_elements=content_features.get("visual_elements", "无"),
            )

            logger.info(
                f"🎯 内容分析完成: {result.primary_domain.value}领域, 置信度: {result.confidence:.2f}"
            )
            return result

        except Exception as e:
            logger.error(f" 内容分析失败: {e}")
            # 返回默认分析结果
            return ContentAnalysisResult(
                primary_domain=ContentDomain.GENERAL,
                secondary_domains=[],
                confidence=0.5,
                key_topics=[],
                content_style="讲解式",
                target_audience="通用",
                content_length="中等",
                visual_elements=[],
            )

    async def _basic_content_analysis(self, transcript: str) -> Dict[str, Any]:
        """基础内容分析"""
        system_prompt = """你是一个专业的内容分析专家。请分析以下转录文本的基本特征。

请以JSON格式返回分析结果，包含以下字段：
{
    "main_theme": "主要主题",
    "key_topics": ["关键话题1", "关键话题2", "关键话题3"],
    "content_summary": "内容概要（50字以内）",
    "language_style": "语言风格（正式/非正式/专业/通俗）",
    "emotional_tone": "情感基调（积极/中性/消极）"
}

请确保返回有效的JSON格式。"""

        user_prompt = f"请分析以下转录内容：\n\n{transcript[:2000]}"

        try:
            response = await self.ai_client.generate_content(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=500,
                temperature=0.3,
            )

            # 解析JSON响应
            analysis = json.loads(response.strip())
            return analysis

        except json.JSONDecodeError:
            logger.warning("⚠️ AI返回的JSON格式无效，使用默认分析")
            return {
                "main_theme": "未知主题",
                "key_topics": [],
                "content_summary": "内容分析失败",
                "language_style": "通俗",
                "emotional_tone": "中性",
            }
        except Exception as e:
            logger.error(f"基础内容分析失败: {e}")
            return {
                "main_theme": "未知主题",
                "key_topics": [],
                "content_summary": "内容分析失败",
                "language_style": "通俗",
                "emotional_tone": "中性",
            }

    async def _domain_classification(
        self, transcript: str, basic_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """领域分类"""
        # 构建领域描述
        domain_descriptions = {
            ContentDomain.EDUCATION: "教育学习：包含教学、培训、知识讲解、技能传授等内容",
            ContentDomain.EXAM_REVIEW: "试卷评讲：包含试题解析、答案讲解、解题思路、考点分析等内容",
            ContentDomain.MEETING: "会议纪要：包含会议讨论、决议汇报、工作安排、项目进展等内容",
            ContentDomain.TRAVEL: "旅游探索：包含旅行攻略、景点介绍、文化体验等内容",
            ContentDomain.COOKING: "烹饪美食：包含菜谱制作、烹饪技巧、美食分享等内容",
            ContentDomain.LIFESTYLE: "生活方式：包含日常生活、家居装修、时尚搭配等内容",
            ContentDomain.TECHNOLOGY: "科技数码：包含技术讲解、产品评测、科技资讯等内容",
            ContentDomain.BUSINESS: "商业财经：包含商业分析、投资理财、创业经验等内容",
            ContentDomain.HEALTH: "健康养生：包含健康知识、运动健身、医疗保健等内容",
            ContentDomain.ENTERTAINMENT: "娱乐休闲：包含影视评论、游戏攻略、娱乐资讯等内容",
            ContentDomain.NEWS: "新闻资讯：包含时事新闻、社会热点、政治经济等内容",
            ContentDomain.SPORTS: "体育运动：包含体育赛事、运动技巧、健身训练等内容",
        }

        domains_text = "\n".join(
            [
                f"- {domain.value}: {desc}"
                for domain, desc in domain_descriptions.items()
            ]
        )

        system_prompt = f"""你是一个专业的内容领域分类专家。请根据转录内容判断其所属的主要领域。

可选领域：
{domains_text}

Please以JSON格式返回分类结果：
{{
    "primary_domain": "主要领域（从上述领域中选择一个）",
    "secondary_domains": ["次要领域1", "次要领域2"],
    "confidence": 0.85,
    "reasoning": "分类理由"
}}

Please确保返回有效的JSON格式，primary_domain必须是上述领域之一。"""

        user_prompt = f"""请对以下内容进行领域分类：

主题：{basic_analysis.get('main_theme', '未知') if basic_analysis else '未知'}
关键话题：{', '.join(basic_analysis.get('key_topics', [])) if basic_analysis else '无'}
内容概要：{basic_analysis.get('content_summary', '') if basic_analysis else '无'}

转录内容（前2000字符）：
{transcript[:2000]}"""

        try:
            response = await self.ai_client.generate_content(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=300,
                temperature=0.2,
            )

            classification = json.loads(response.strip())

            # 验证和转换领域
            primary_domain = self._validate_domain(
                classification.get("primary_domain", "general")
            )
            secondary_domains = [
                self._validate_domain(domain)
                for domain in classification.get("secondary_domains", [])
            ]

            return {
                "primary_domain": primary_domain,
                "secondary_domains": secondary_domains,
                "confidence": float(classification.get("confidence", 0.5)),
                "reasoning": classification.get("reasoning", ""),
            }

        except Exception as e:
            logger.error(f"领域分类失败: {e}")
            # 使用关键词匹配作为备选方案
            return self._keyword_based_classification(transcript)

    def _validate_domain(self, domain_str: str) -> ContentDomain:
        """验证并转换领域字符串"""
        try:
            return ContentDomain(domain_str.lower())
        except ValueError:
            # 如果不是有效的枚举值，尝试映射
            domain_mapping = {
                "教育": ContentDomain.EDUCATION,
                "学习": ContentDomain.EDUCATION,
                "试卷": ContentDomain.EXAM_REVIEW,
                "评讲": ContentDomain.EXAM_REVIEW,
                "解析": ContentDomain.EXAM_REVIEW,
                "题目": ContentDomain.EXAM_REVIEW,
                "考试": ContentDomain.EXAM_REVIEW,
                "会议": ContentDomain.MEETING,
                "讨论": ContentDomain.MEETING,
                "决议": ContentDomain.MEETING,
                "汇报": ContentDomain.MEETING,
                "纪要": ContentDomain.MEETING,
                "旅游": ContentDomain.TRAVEL,
                "旅行": ContentDomain.TRAVEL,
                "烹饪": ContentDomain.COOKING,
                "美食": ContentDomain.COOKING,
                "做饭": ContentDomain.COOKING,
                "生活": ContentDomain.LIFESTYLE,
                "科技": ContentDomain.TECHNOLOGY,
                "技术": ContentDomain.TECHNOLOGY,
                "商业": ContentDomain.BUSINESS,
                "健康": ContentDomain.HEALTH,
                "娱乐": ContentDomain.ENTERTAINMENT,
                "新闻": ContentDomain.NEWS,
                "体育": ContentDomain.SPORTS,
            }
            return domain_mapping.get(domain_str, ContentDomain.GENERAL)

    def _keyword_based_classification(self, transcript: str) -> Dict[str, Any]:
        """基于关键词的分类（备选方案）"""
        transcript_lower = transcript.lower()
        domain_scores = {}

        # 计算每个领域的匹配分数
        for domain, keywords in self.domain_keywords.items():
            score = sum(1 for keyword in keywords if keyword in transcript_lower)
            if score > 0:
                domain_scores[domain] = score / len(keywords)

        if not domain_scores:
            return {
                "primary_domain": ContentDomain.GENERAL,
                "secondary_domains": [],
                "confidence": 0.3,
                "reasoning": "关键词匹配失败，使用默认分类",
            }

        # 排序获取主要和次要领域
        sorted_domains = sorted(domain_scores.items(), key=lambda x: x[1], reverse=True)
        primary_domain = sorted_domains[0][0]
        secondary_domains = [
            domain for domain, score in sorted_domains[1:3] if score > 0.1
        ]

        return {
            "primary_domain": primary_domain,
            "secondary_domains": secondary_domains,
            "confidence": min(sorted_domains[0][1] * 2, 0.8),
            "reasoning": "基于关键词匹配的分类结果",
        }

    async def _analyze_content_features(
        self, transcript: str, **kwargs
    ) -> Dict[str, Any]:
        """分析内容特征"""
        # 分析内容长度
        word_count = len(transcript)
        if word_count < 500:
            content_length = "短"
        elif word_count < 2000:
            content_length = "中等"
        else:
            content_length = "长"

        # 分析内容风格（基于语言特征）
        content_style = self._analyze_content_style(transcript)

        # 分析目标受众
        target_audience = self._analyze_target_audience(transcript)

        # 分析视觉元素（基于帧信息）
        visual_elements = self._analyze_visual_elements(kwargs)

        return {
            "content_style": content_style,
            "target_audience": target_audience,
            "content_length": content_length,
            "visual_elements": visual_elements,
        }

    def _analyze_content_style(self, transcript: str) -> str:
        """分析内容风格"""
        # 简单的风格判断逻辑
        if "大家好" in transcript or "我们来" in transcript:
            return "讲解式"
        elif "?" in transcript or "吗" in transcript:
            return "对话式"
        elif "步骤" in transcript or "第一" in transcript or "首先" in transcript:
            return "教程式"
        elif "演示" in transcript or "展示" in transcript:
            return "演示式"
        else:
            return "叙述式"

    def _analyze_target_audience(self, transcript: str) -> str:
        """分析目标受众"""
        if "初学者" in transcript or "新手" in transcript or "入门" in transcript:
            return "初学者"
        elif "高级" in transcript or "专业" in transcript or "深入" in transcript:
            return "专业人士"
        elif "进阶" in transcript or "提升" in transcript:
            return "进阶者"
        else:
            return "通用受众"

    def _analyze_visual_elements(self, kwargs: Dict[str, Any]) -> List[str]:
        """分析视觉元素"""
        visual_elements = []

        # 基于帧信息判断
        frame_info = kwargs.get("frame_info", {})
        frames = frame_info.get("frames", [])

        if frames:
            visual_elements.append("视频帧")
            if len(frames) > 10:
                visual_elements.append("丰富画面")

        # 基于文本内容判断
        transcript = kwargs.get("transcript", "")
        if "图表" in transcript or "数据" in transcript:
            visual_elements.append("数据图表")
        if "演示" in transcript or "操作" in transcript:
            visual_elements.append("操作演示")
        if "实物" in transcript or "产品" in transcript:
            visual_elements.append("实物展示")

        return visual_elements or ["文本内容"]

    async def generate_dynamic_prompt(
        self, analysis_result: ContentAnalysisResult, content_type: str = "content_card"
    ) -> Dict[str, str]:
        """
        根据内容分析结果生成动态提示词

        Args:
            analysis_result: 内容分析结果
            content_type: 内容类型（content_card, mind_map, flashcards, ai_analysis）

        Returns:
            Dict[str, str]: 包含system_prompt和user_prompt的字典
        """
        try:
            # 获取领域专用的提示词模板
            domain_template = self._get_domain_template(
                analysis_result.primary_domain, content_type
            )

            # 根据内容特征调整提示词
            adjusted_template = self._adjust_template_by_features(
                domain_template, analysis_result
            )

            # 生成最终的提示词
            system_prompt = adjusted_template["system_prompt"]
            user_prompt_template = adjusted_template["user_prompt_template"]

            logger.info(
                f"🎨 为{analysis_result.primary_domain.value}领域生成了动态{content_type}提示词"
            )

            return {
                "system_prompt": system_prompt,
                "user_prompt_template": user_prompt_template,
            }

        except Exception as e:
            logger.error(f"❌ 动态提示词生成失败: {e}")
            # 返回通用提示词
            return self._get_fallback_prompt(content_type)

    def _get_domain_template(
        self, domain: ContentDomain, content_type: str
    ) -> Dict[str, str]:
        """获取领域专用的提示词模板"""

        # 领域专用的系统提示词模板
        domain_system_prompts = {
            ContentDomain.EXAM_REVIEW: {
                "content_card": """# 角色设定
你是一位资深的试卷评讲专家，专门将试卷评讲视频转化为结构化的学习资料。

# 专业特长
- 深度理解各学科试题的解题思路和考点分析
- 擅长将复杂题目的解题过程分解为清晰的步骤
- 能够识别学生易错点和关键考察点
- 精通各类题型的解题方法和技巧总结

# 内容质量标准
1. **题目完整性**：确保每道题的题目、答案、解析都完整呈现
2. **解题逻辑清晰**：每个解题步骤都要有明确的逻辑推理
3. **考点精准定位**：准确识别每道题考察的知识点和能力要求
4. **易错点突出**：重点标注学生容易出错的地方和原因
5. **方法技巧总结**：提炼解题的通用方法和应试技巧

# 试卷评讲特色
- 使用专业的学科术语和解题语言
- 强调解题思路的逻辑性和系统性
- 提供多种解题方法的对比分析
- 包含举一反三的拓展练习建议

# 内容结构要求
- 按题目顺序逐一分析，每道题独立成段
- 每道题包含：题目内容、正确答案、详细解析、易错分析、方法总结
- 突出重点题型和高频考点
- 提供学习建议和复习要点""",
                "mind_map": """你是试卷评讲结构化专家，擅长将试题内容转化为清晰的知识体系思维导图。

重点关注：
- 考点的分布和权重
- 题型的分类和特点
- 解题方法的系统梳理
- 知识点间的关联关系

输出要求：
- 主干体现核心考点模块
- 分支展现具体题型和方法
- 层次不超过3级
- 突出重点和难点题目""",
                "flashcards": """你是试卷评讲学习卡片专家，专门创建针对性的复习闪卡。

重点内容：
- 核心题型的解题方法
- 重要公式和定理应用
- 易错点和注意事项
- 解题技巧和思路总结

卡片特色：
- 问题针对具体题型
- 答案包含完整解题过程
- 突出关键步骤和方法
- 提供类似题目的解题思路""",
            },
            ContentDomain.EDUCATION: {
                "content_card": """# 角色设定
你是一位资深的教育内容专家，专门将教学视频转化为结构化的学习卡片。

# 专业特长
- 深度理解教育心理学和学习理论
- 擅长知识点的层次化组织和逻辑梳理
- 能够识别学习重点和难点
- 精通教学方法和学习策略

# 内容质量标准
1. **知识体系完整**：确保知识点覆盖全面，逻辑清晰
2. **学习导向明确**：突出学习目标和核心概念
3. **实践应用结合**：提供具体的应用场景和练习建议
4. **难度梯度合理**：从基础概念到深入理解，循序渐进

# 教育内容特色
- 使用教育术语和专业表达
- 强调知识点的前后关联
- 提供学习方法和记忆技巧
- 包含自我检测和反思问题""",
                "mind_map": """你是教育内容结构化专家，擅长将教学内容转化为清晰的知识体系思维导图。

重点关注：
- 知识点的层次关系
- 概念间的逻辑联系  
- 学习路径的规划
- 重点难点的标识

输出要求：
- 主干体现核心知识模块
- 分支展现具体知识点
- 层次不超过3级
- 每个节点简洁明确""",
            },
            ContentDomain.COOKING: {
                "content_card": """# 角色设定
你是一位专业的美食内容创作专家，专门将烹饪视频转化为实用的料理指南。

# 专业特长
- 深入了解各种烹饪技巧和食材特性
- 擅长菜谱的标准化整理和步骤优化
- 能够提供营养搭配和健康建议
- 精通中西料理文化和传统工艺

# 内容质量标准
1. **操作性强**：每个步骤清晰可执行，新手也能跟做
2. **细节丰富**：包含火候、时间、用量等关键细节
3. **技巧传授**：分享烹饪窍门和经验心得
4. **营养健康**：关注食材营养和健康搭配

# 美食内容特色
- 使用生动的美食描述语言
- 强调口感、色泽、香味等感官体验
- 提供食材替换和口味调整建议
- 包含文化背景和制作故事""",
                "flashcards": """你是美食教学专家，专门创建实用的烹饪学习卡片。

重点内容：
- 食材处理技巧
- 烹饪方法要点
- 调味搭配原理
- 常见问题解决

卡片特色：
- 问题实用具体
- 答案详细易懂
- 包含实操提示
- 突出关键技巧""",
            },
            ContentDomain.MEETING: {
                "content_card": """# 角色设定
你是一位专业的会议纪要专家，专门将会议录音转化为结构化的会议纪要和行动计划。

# 专业特长
- 深度理解会议流程和决策机制
- 擅长提炼关键决议和行动要点
- 能够识别责任分工和时间节点
- 精通会议纪要的标准化格式

# 内容质量标准
1. **信息完整性**：准确记录所有重要决议和讨论要点
2. **逻辑清晰性**：按议题分类，突出因果关系
3. **行动导向性**：明确责任人、时间节点和具体行动
4. **可追溯性**：便于后续跟进和执行检查

# 会议纪要特色
- 使用正式的商务语言
- 强调决议的可执行性
- 提供清晰的责任分工
- 包含风险提示和后续安排""",
                "mind_map": """你是会议管理专家，擅长将会议内容整理成清晰的决策树和行动图。

重点关注：
- 核心议题和决议
- 责任分工和时间线
- 问题识别和解决方案
- 后续行动和跟进要点

结构要求：
- 按议题或部门分类
- 突出关键决议和行动
- 明确责任人和时间节点
- 体现决策逻辑和依据""",
                "flashcards": """你是会议管理专家，专门创建会议要点的学习卡片。

重点内容：
- 关键决议和背景
- 重要行动项和责任人
- 时间节点和里程碑
- 风险点和应对措施

卡片特色：
- 问题聚焦具体决议
- 答案包含执行要点
- 突出责任和时间
- 提供跟进提醒""",
            },
            ContentDomain.TRAVEL: {
                "content_card": """# 角色设定
你是一位资深的旅行内容专家，专门将旅游视频转化为实用的旅行攻略。

# 专业特长
- 深度了解各地文化风俗和旅游资源
- 擅长行程规划和预算控制
- 能够提供实用的旅行建议和注意事项
- 精通摄影技巧和旅行记录方法

# 内容质量标准
1. **实用性强**：提供具体可行的旅行建议
2. **信息详实**：包含交通、住宿、美食、景点等全面信息
3. **体验导向**：突出独特的旅行体验和文化感受
4. **安全贴心**：关注旅行安全和注意事项

# 旅行内容特色
- 使用生动的旅行描述语言
- 强调文化体验和人文感受
- 提供预算参考和性价比分析
- 包含摄影建议和最佳时机""",
                "mind_map": """你是旅行攻略规划专家，擅长将旅游内容整理成系统的出行指南。

重点关注：
- 目的地核心亮点
- 行程安排逻辑
- 实用信息整理
- 体验价值评估

结构要求：
- 按地区或主题分类
- 突出必游和推荐
- 包含实用信息
- 体现个人体验""",
            },
        }

        # 获取对应的模板，如果没有则使用通用模板
        domain_templates = domain_system_prompts.get(domain, {})
        template = domain_templates.get(content_type)

        if template:
            return {
                "system_prompt": template,
                "user_prompt_template": "请为以下{domain}内容生成{content_type}：\n\n{transcript}\n\n请确保内容针对{target_audience}，采用{content_style}的表达方式。",
            }
        else:
            return {
                "system_prompt": self._get_general_template(content_type),
                "user_prompt_template": "请为以下内容生成{content_type}：\n\n{transcript}",
            }

    def _get_general_template(self, content_type: str) -> str:
        """获取通用模板"""
        general_templates = {
            "content_card": """# 角色设定
你是一位资深的内容专家，擅长将各类视频内容转化为结构化的知识卡片。

# 核心能力
- 深入理解内容主题和核心价值
- 擅长信息的结构化整理和逻辑梳理
- 能够提炼关键信息和核心观点
- 精通内容的可读性和实用性优化

# 内容质量标准
1. **结构清晰**：逻辑层次分明，易于理解
2. **信息完整**：覆盖核心内容，不遗漏重点
3. **表达生动**：语言流畅，富有感染力
4. **实用价值**：对读者有实际帮助和启发""",
            "mind_map": """你是内容结构化专家，擅长将复杂内容转化为清晰的思维导图。

重点关注：
- 主题的核心要素
- 内容的逻辑关系
- 信息的层次结构
- 关键点的突出

输出要求：
- 主干体现核心主题
- 分支展现关键要素
- 层次控制在3级以内
- 节点简洁有力""",
        }

        return general_templates.get(content_type, "你是一位专业的内容专家。")

    def _adjust_template_by_features(
        self, base_template: Dict[str, str], analysis_result: ContentAnalysisResult
    ) -> Dict[str, str]:
        """根据内容特征调整模板"""

        # 根据目标受众调整
        audience_adjustments = {
            "初学者": "特别注意使用简单易懂的语言，多提供基础概念解释",
            "专业人士": "可以使用专业术语，深入分析技术细节",
            "进阶者": "在基础之上提供进阶技巧和深度思考",
        }

        # 根据内容风格调整
        style_adjustments = {
            "讲解式": "保持教学的严谨性和逻辑性",
            "对话式": "体现互动性，使用更加亲近的语言",
            "演示式": "重点关注操作步骤和实践要点",
            "教程式": "按照教程的逻辑结构组织内容",
        }

        # 确保 base_template 是字典格式
        if isinstance(base_template, dict):
            system_prompt = base_template.get("system_prompt", "")
            user_prompt_template = base_template.get("user_prompt_template", "")
        else:
            # 如果 base_template 不是字典，则创建一个新的字典
            system_prompt = str(base_template) if base_template else ""
            user_prompt_template = "请为以下{domain}内容生成{content_type}：\n\n{transcript}\n\n请确保内容针对{target_audience}，采用{content_style}的表达方式。"

        # 构建调整后的系统提示词
        adjusted_prompt = system_prompt

        if analysis_result.target_audience in audience_adjustments:
            adjusted_prompt += f"\n\n# 目标受众调整\n{audience_adjustments[analysis_result.target_audience]}"

        if analysis_result.content_style in style_adjustments:
            adjusted_prompt += f"\n\n# 内容风格调整\n{style_adjustments[analysis_result.content_style]}"

        # 根据关键话题添加专业指导
        if analysis_result.key_topics:
            topics_text = "、".join(analysis_result.key_topics[:3])
            adjusted_prompt += f"\n\n# 核心话题\n重点关注以下话题：{topics_text}"

        return {
            "system_prompt": adjusted_prompt,
            "user_prompt_template": user_prompt_template,
        }

    async def generate_dynamic_prompt_for_role(
        self,
        force_domain: str,
        content_type: str,
        analysis_result: ContentAnalysisResult,
    ) -> Dict[str, str]:
        """
        为强制指定的角色生成动态提示词

        Args:
            force_domain: 强制指定的角色/领域
            content_type: 内容类型
            analysis_result: 分析结果（包含强制角色信息）

        Returns:
            Dict[str, str]: 包含system_prompt和user_prompt_template的字典
        """
        try:
            # 从配置文件读取角色提示词模板
            from biz.routes.settings_api import get_role_name, get_prompt_template

            # 获取角色的专业名称
            role_name = get_role_name(force_domain, "content_card", "内容专家")

            # 获取内容类型对应的提示词模板
            system_template = get_prompt_template(content_type, "system_prompt")
            user_template = get_prompt_template(content_type, "user_prompt")

            if system_template and user_template:
                # 使用配置文件中的模板
                logger.info(f"🎯 使用配置文件中的{content_type}模板")

                # 格式化系统提示词
                system_prompt = system_template.format(
                    role_name=role_name,
                    domain=force_domain,
                    target_audience="通用受众",
                    key_topics="用户指定内容",
                )

                # 用户提示词模板
                user_prompt_template = user_template

            else:
                # 使用默认的角色特定提示词
                logger.info(f"🎯 使用默认的{force_domain}角色提示词")
                system_prompt = f"""# 角色
你是一位专业的{role_name}，擅长将{force_domain}领域的视频内容转化为结构化、高质量的知识卡片。

# 核心能力
- 深入理解{force_domain}领域的专业知识和特色
- 擅长信息的结构化整理和逻辑梳理
- 能够提炼关键信息和核心观点
- 精通内容的可读性和实用性优化

# 内容质量标准
1. **结构清晰**：逻辑层次分明，易于理解
2. **信息完整**：覆盖核心内容，不遗漏重点
3. **表达生动**：语言流畅，富有感染力
4. **专业准确**：体现{force_domain}领域的专业特色

# 🚫 严禁AI助手语言
- ❌ 绝对禁止："当然可以！"、"以下是"、"我来为您"、"让我"
- ❌ 绝对禁止："希望对您有帮助"、"欢迎告诉我"、"需要其他版本"
- ❌ 绝对禁止：任何AI角色扮演、客服语言、推广话语
- ✅ 要求：直接开始内容，直接结束内容，零AI痕迹"""

                user_prompt_template = f"""请为以下{force_domain}领域内容生成专业的{content_type}：

## 转录内容：
{{transcript}}

请确保内容体现{force_domain}领域的专业特色，结构清晰，信息完整。"""

            return {
                "system_prompt": system_prompt,
                "user_prompt_template": user_prompt_template,
            }

        except Exception as e:
            logger.error(f"❌ 角色提示词生成失败: {e}")
            # 返回基础的角色提示词
            return {
                "system_prompt": f"你是一位专业的{force_domain}专家，请生成高质量的内容。",
                "user_prompt_template": f"请为以下{force_domain}内容生成{{content_type}}：\n\n{{transcript}}",
            }

    def _get_fallback_prompt(self, content_type: str) -> Dict[str, str]:
        """获取备用提示词"""
        return {
            "system_prompt": "你是一位专业的内容专家，请根据提供的内容生成高质量的结构化输出。",
            "user_prompt_template": "请为以下内容生成{content_type}：\n\n{transcript}",
        }


# 便捷函数
async def analyze_and_generate_prompt(
    ai_client, transcript: str, content_type: str = "content_card", **kwargs
) -> Tuple[ContentAnalysisResult, Dict[str, str]]:
    """
    分析内容并生成动态提示词的便捷函数

    Args:
        ai_client: AI客户端
        transcript: 转录文本
        content_type: 内容类型
        **kwargs: 其他参数，包括force_domain用于强制指定角色

    Returns:
        Tuple[ContentAnalysisResult, Dict[str, str]]: (分析结果, 提示词字典)
    """
    analyzer = AIContentAnalyzer(ai_client)

    # 🎯 检查是否强制指定了角色
    force_domain = kwargs.get("force_domain")

    if force_domain and force_domain != "auto":
        # 强制使用指定的角色，跳过智能分析
        logger.info(f"🎯 强制使用指定角色: {force_domain}")

        # 将字符串转换为ContentDomain枚举
        domain_mapping = {
            "education": ContentDomain.EDUCATION,
            "exam_review": ContentDomain.EXAM_REVIEW,
            "meeting": ContentDomain.MEETING,
            "travel": ContentDomain.TRAVEL,
            "cooking": ContentDomain.COOKING,
            "technology": ContentDomain.TECHNOLOGY,
            "business": ContentDomain.BUSINESS,
            "health": ContentDomain.HEALTH,
            "it": ContentDomain.TECHNOLOGY,  # IT映射到technology
            "finance": ContentDomain.BUSINESS,  # finance映射到business
            "biography": ContentDomain.GENERAL,  # 人物志暂时映射到general
            "movie": ContentDomain.ENTERTAINMENT,  # 电影映射到entertainment
            "chinese_anime": ContentDomain.ENTERTAINMENT,  # 国漫映射到entertainment
            "japanese_anime": ContentDomain.ENTERTAINMENT,  # 日漫映射到entertainment
            "general": ContentDomain.GENERAL,
        }

        domain_enum = domain_mapping.get(force_domain, ContentDomain.GENERAL)

        # 创建强制分析结果
        analysis_result = ContentAnalysisResult(
            primary_domain=domain_enum,
            secondary_domains=[],
            confidence=1.0,  # 强制指定的置信度为100%
            key_topics=["用户指定角色"],
            content_style="讲解式",
            target_audience="通用受众",
            content_length="中等",
            visual_elements=[],
        )

        # 使用强制指定的角色生成提示词
        prompts = await analyzer.generate_dynamic_prompt_for_role(
            force_domain, content_type, analysis_result
        )

    else:
        # 使用智能分析
        logger.info("🤖 使用智能分析确定角色")
        analysis_result = await analyzer.analyze_content(transcript, **kwargs)
        prompts = await analyzer.generate_dynamic_prompt(analysis_result, content_type)

    return analysis_result, prompts


# 测试代码
if __name__ == "__main__":

    async def test_analyzer():
        """测试内容分析器"""
        from core.ai.ai_chat_client import create_ai_client
        import json

        # 加载配置
        settings_path = Path("config/settings.json")
        if settings_path.exists():
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
        else:
            print("❌ 未找到配置文件")
            return

        # 创建AI客户端
        ai_client = create_ai_client("openai", settings)
        analyzer = AIContentAnalyzer(ai_client)

        # 测试文本
        test_transcript = """
        大家好，今天我来教大家如何制作正宗的宫保鸡丁。这道菜是川菜的经典代表，
        口感酸甜适中，鸡肉嫩滑，花生米香脆。首先我们需要准备食材：鸡胸肉300克，
        花生米100克，干辣椒10个，花椒20粒。调料需要生抽、老抽、料酒、白糖、
        香醋、淀粉等。制作步骤很重要，第一步是处理鸡肉，要切成1厘米见方的丁，
        然后用料酒和淀粉腌制15分钟。第二步是炸花生米，油温要控制在六成热...
        """

        print("🧪 开始测试内容分析器...")

        # 分析内容
        result = await analyzer.analyze_content(test_transcript)
        print(f"📊 分析结果:")
        print(f"  主要领域: {result.primary_domain.value}")
        print(f"  次要领域: {[d.value for d in result.secondary_domains]}")
        print(f"  置信度: {result.confidence:.2f}")
        print(f"  关键话题: {result.key_topics}")
        print(f"  内容风格: {result.content_style}")
        print(f"  目标受众: {result.target_audience}")

        # 生成动态提示词
        prompts = await analyzer.generate_dynamic_prompt(result, "content_card")
        print(f"\n🎨 动态提示词生成完成")
        print(f"系统提示词长度: {len(prompts['system_prompt'])}")
        print(f"用户提示词模板: {prompts['user_prompt_template'][:100]}...")

    import asyncio

    asyncio.run(test_analyzer())
