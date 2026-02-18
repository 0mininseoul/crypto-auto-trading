"""
AI 차트 분석 모듈
Gemini API를 활용한 트레이딩 분석
"""

__all__ = ["ChartAnalyzer", "get_chart_analyzer"]


def __getattr__(name):
    if name == "ChartAnalyzer":
        from src.ai.chart_analyzer import ChartAnalyzer
        return ChartAnalyzer
    if name == "get_chart_analyzer":
        from src.ai.chart_analyzer import get_chart_analyzer
        return get_chart_analyzer
    raise AttributeError(f"module 'src.ai' has no attribute {name!r}")
