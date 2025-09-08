#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI内容生成工厂单元测试
"""

import pytest
import asyncio
from pathlib import Path
import sys

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from biz.services.ai_content_generator import (
    AIContentFactory, 
    OutputType, 
    generate_content, 
    generate_all_content
)


class TestAIContentFactory:
    """AI内容生成工厂测试类"""
    
    @pytest.fixture
    def factory(self):
        """创建工厂实例"""
        return AIContentFactory()
    
    @pytest.mark.asyncio
    async def test_factory_creation(self, factory):
        """测试工厂创建"""
        assert factory is not None
        assert isinstance(factory, AIContentFactory)
        assert factory.output_dir.exists()
    
    @pytest.mark.asyncio
    async def test_generate_content_card(self, factory):
        """测试生成内容卡片"""
        result = await factory.generate("content_card", language="zh")
        
        assert result["success"] is True
        assert result["type"] == "content_card"
        assert "内容卡片" in result["content"]
        assert result["format"] == "markdown"
    
    @pytest.mark.asyncio
    async def test_generate_mind_map(self, factory):
        """测试生成思维导图"""
        result = await factory.generate("mind_map", language="zh")
        
        assert result["success"] is True
        assert result["type"] == "mind_map"
        assert "思维导图" in result["content"]
        assert result["format"] == "markdown"
    
    @pytest.mark.asyncio
    async def test_generate_flashcards(self, factory):
        """测试生成闪卡"""
        result = await factory.generate("flashcards", language="zh")
        
        assert result["success"] is True
        assert result["type"] == "flashcards"
        assert "学习闪卡" in result["content"]
        assert result["format"] == "markdown"
    
    @pytest.mark.asyncio
    async def test_generate_ai_analysis(self, factory):
        """测试生成AI分析"""
        result = await factory.generate("ai_analysis", language="zh")
        
        assert result["success"] is True
        assert result["type"] == "ai_analysis"
        assert "AI分析结果" in result["content"]
        assert result["format"] == "json"
    
    @pytest.mark.asyncio
    async def test_generate_all(self, factory):
        """测试批量生成"""
        result = await factory.generate_all(language="zh")
        
        assert result["success"] is True
        assert "results" in result
        assert len(result["results"]) == 4
        
        # 检查所有类型都已生成
        expected_types = ["content_card", "mind_map", "flashcards", "ai_analysis"]
        for expected_type in expected_types:
            assert expected_type in result["results"]
            assert result["results"][expected_type]["success"] is True
    
    @pytest.mark.asyncio
    async def test_invalid_output_type(self, factory):
        """测试无效的输出类型"""
        result = await factory.generate("invalid_type", language="zh")
        
        assert result["success"] is False
        assert "error" in result
        assert "不支持的输出类型" in result["error"]
    
    @pytest.mark.asyncio
    async def test_convenience_functions(self):
        """测试便捷函数"""
        # 测试单个生成
        result = await generate_content("content_card", language="zh")
        assert result["success"] is True
        assert result["type"] == "content_card"
        
        # 测试批量生成
        all_results = await generate_all_content(language="zh")
        assert all_results["success"] is True
        assert len(all_results["results"]) == 4


if __name__ == "__main__":
    # 直接运行测试
    pytest.main([__file__, "-v"])
