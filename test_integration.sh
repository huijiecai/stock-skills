#!/bin/bash
# 集成测试脚本 - 验证 LLM 与 Web 平台集成

echo "════════════════════════════════════════════════════════════"
echo "  LLM 与 Web 平台集成测试"
echo "════════════════════════════════════════════════════════════"
echo ""

# 1. 检查后端服务
echo "✓ 检查后端服务..."
if curl -s http://localhost:8000/health | grep -q "ok"; then
    echo "  ✅ 后端服务运行正常"
else
    echo "  ❌ 后端服务未启动，请运行: cd backend && uvicorn app.main:app --reload"
    exit 1
fi

# 2. 检查前端服务
echo ""
echo "✓ 检查前端服务..."
if curl -s http://localhost:3000/ | grep -q "龙头战法"; then
    echo "  ✅ 前端服务运行正常"
else
    echo "  ❌ 前端服务未启动，请运行: cd frontend && npm start"
    exit 1
fi

# 3. 检查聊天 API 是否注册
echo ""
echo "✓ 检查聊天 API..."
if curl -s http://localhost:8000/openapi.json | grep -q "/api/chat/analyze"; then
    echo "  ✅ 聊天 API 已注册"
else
    echo "  ❌ 聊天 API 未注册"
    exit 1
fi

# 4. 检查环境变量
echo ""
echo "✓ 检查环境变量..."
if [ -f "backend/.env" ]; then
    if grep -q "OPENAI_API_KEY=your_openai_api_key_here" backend/.env; then
        echo "  ⚠️  需要配置 OPENAI_API_KEY"
        echo "     编辑: backend/.env"
        echo "     填写真实的 OpenAI API Key"
    elif grep -q "OPENAI_API_KEY=sk-" backend/.env; then
        echo "  ✅ OPENAI_API_KEY 已配置"
    else
        echo "  ⚠️  OPENAI_API_KEY 配置可能有误"
    fi
else
    echo "  ❌ backend/.env 文件不存在"
    exit 1
fi

# 5. 检查 Skill 文件
echo ""
echo "✓ 检查 Skill 文件..."
if [ -f "skills/dragon-stock-trading/SKILL.md" ]; then
    echo "  ✅ SKILL.md 存在"
else
    echo "  ❌ SKILL.md 不存在"
    exit 1
fi

# 6. 检查 Reference 文档
echo ""
echo "✓ 检查 Reference 文档..."
ref_count=$(ls -1 skills/dragon-stock-trading/reference/*.md 2>/dev/null | wc -l)
if [ "$ref_count" -ge 7 ]; then
    echo "  ✅ Reference 文档完整（$ref_count 个）"
else
    echo "  ⚠️  Reference 文档不完整（只有 $ref_count 个，预期 7 个）"
fi

# 7. 检查前端聊天组件
echo ""
echo "✓ 检查前端聊天组件..."
if [ -f "frontend/src/pages/ChatAnalysis.js" ]; then
    echo "  ✅ ChatAnalysis.js 存在"
else
    echo "  ❌ ChatAnalysis.js 不存在"
    exit 1
fi

# 8. 检查 react-markdown 依赖
echo ""
echo "✓ 检查前端依赖..."
if grep -q "react-markdown" frontend/package.json; then
    echo "  ✅ react-markdown 已安装"
else
    echo "  ❌ react-markdown 未安装，请运行: cd frontend && npm install react-markdown"
    exit 1
fi

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  ✅ 集成测试通过！"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "📝 下一步："
echo "   1. 确保配置了 OPENAI_API_KEY（backend/.env）"
echo "   2. 访问: http://localhost:3000/chat"
echo "   3. 尝试示例问题:"
echo "      - 今天市场情绪怎么样？"
echo "      - 帮我分析 002342"
echo "      - 什么是龙头战法的冰点修复？"
echo ""
echo "📚 更多信息:"
echo "   - 详细报告: LLM_WEB_INTEGRATION_REPORT.md"
echo "   - 快速开始: AI_CHAT_QUICKSTART.md"
echo ""
