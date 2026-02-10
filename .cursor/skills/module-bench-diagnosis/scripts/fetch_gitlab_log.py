#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitLab Job Log Fetcher

从 GitLab job URL 获取日志，支持多种分析模式。

环境变量：
- GITLAB_TOKEN: GitLab Personal Access Token (必需)
- GITLAB_URL: GitLab 实例地址 (可选，默认 https://code.deeproute.ai)

用法：
  python fetch_gitlab_log.py <job_url> [options]
  
选项：
  --full          输出完整日志（默认只输出错误相关和最后500行）
  --tsan          提取 ThreadSanitizer 详细报告
  --search=PATTERN  搜索指定模式并输出上下文
  
示例：
  python fetch_gitlab_log.py https://gitlab.com/myproject/myrepo/-/jobs/123456
  python fetch_gitlab_log.py https://gitlab.com/myproject/myrepo/-/jobs/123456 --full
  python fetch_gitlab_log.py https://gitlab.com/myproject/myrepo/-/jobs/123456 --tsan
"""

import os
import re
import sys
import urllib.parse
import urllib.request
import urllib.error
import json
import time
import random
import socket

TOKEN = os.environ.get('GITLAB_TOKEN')
GITLAB_BASE_URL = os.environ.get('GITLAB_URL', 'https://code.deeproute.ai')


def parse_job_url(url):
    """
    从 GitLab job URL 中解析项目路径和 job ID
    """
    pattern = r'https?://([^/]+)/(.+?)/-/jobs/(\d+)'
    match = re.match(pattern, url)
    
    if not match:
        raise ValueError(f"无法解析 GitLab job URL: {url}")
    
    gitlab_host = match.group(1)
    project_path = match.group(2)
    job_id = match.group(3)
    
    project_path_encoded = urllib.parse.quote(project_path, safe='')
    
    return gitlab_host, project_path_encoded, job_id


def fetch_job_log(gitlab_url, project_path, job_id, token):
    """
    使用 GitLab API 获取 job 日志
    """
    api_url = f"{gitlab_url}/api/v4/projects/{project_path}/jobs/{job_id}/trace"
    
    request = urllib.request.Request(api_url)
    request.add_header('PRIVATE-TOKEN', token)
    
    max_attempts = 3
    base_delay_sec = 1.0

    def _sleep_before_retry(attempt_idx):
        delay = base_delay_sec * (2 ** (attempt_idx - 1))
        delay += random.uniform(0.0, 0.3)
        time.sleep(delay)

    def _looks_temporary_network_error(err):
        msg = str(err).lower()
        return any(s in msg for s in [
            "timed out", "timeout", "temporary failure",
            "connection reset by peer", "remote end closed connection",
            "connection aborted", "connection refused",
            "network is unreachable", "name or service not known",
        ])

    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                log_content = response.read().decode('utf-8')
                return log_content
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise Exception("认证失败：请检查 GITLAB_TOKEN 是否正确")
            if e.code == 403:
                raise Exception("权限不足：token 没有访问该项目的权限")
            if e.code == 404:
                raise Exception(f"Job 不存在：job_id={job_id}")
            if e.code in (408, 429, 500, 502, 503, 504) and attempt < max_attempts:
                print(f"GitLab API 临时失败（HTTP {e.code}），准备重试 {attempt + 1}/{max_attempts} ...", file=sys.stderr)
                _sleep_before_retry(attempt)
                continue
            raise Exception(f"API 请求失败：HTTP {e.code} - {e.reason}")
        except (urllib.error.URLError, TimeoutError, socket.timeout) as e:
            if attempt < max_attempts:
                print(f"网络请求失败（{e}），准备重试 {attempt + 1}/{max_attempts} ...", file=sys.stderr)
                _sleep_before_retry(attempt)
                continue
            raise Exception(f"网络请求失败：{e}")
        except Exception as e:
            if attempt < max_attempts and _looks_temporary_network_error(e):
                print(f"网络抖动（{e}），准备重试 {attempt + 1}/{max_attempts} ...", file=sys.stderr)
                _sleep_before_retry(attempt)
                continue
            raise Exception(f"网络请求失败：{e}")


def extract_tsan_reports(log_content):
    """
    提取 ThreadSanitizer 详细报告
    
    返回：(summary_lines, detailed_issues)
    """
    lines = log_content.split('\n')
    
    # 提取 SUMMARY 行
    summary_lines = []
    for line in lines:
        if 'SUMMARY: ThreadSanitizer' in line:
            summary_lines.append(line)
    
    # 提取详细的 Issue 报告
    detailed_issues = []
    in_issue = False
    current_issue = []
    issue_count = 0
    
    for i, line in enumerate(lines):
        # 检测 Issue 开始
        if 'WARNING: ThreadSanitizer:' in line:
            if current_issue:
                detailed_issues.append('\n'.join(current_issue))
            current_issue = [f"[Issue #{issue_count + 1}]", line]
            in_issue = True
            issue_count += 1
            continue
        
        # 检测 Issue 结束（遇到 SUMMARY 行）
        if in_issue and 'SUMMARY: ThreadSanitizer' in line:
            current_issue.append(line)
            detailed_issues.append('\n'.join(current_issue))
            current_issue = []
            in_issue = False
            continue
        
        # 收集 Issue 内容
        if in_issue:
            current_issue.append(line)
            # 限制每个 issue 最多 100 行
            if len(current_issue) > 100:
                current_issue.append("... (truncated)")
                detailed_issues.append('\n'.join(current_issue))
                current_issue = []
                in_issue = False
    
    # 处理最后一个 issue
    if current_issue:
        detailed_issues.append('\n'.join(current_issue))
    
    return summary_lines, detailed_issues


def extract_pattern_context(log_content, pattern, context_before=5, context_after=10):
    """
    搜索指定模式并提取上下文
    """
    lines = log_content.split('\n')
    results = []
    
    for i, line in enumerate(lines):
        if re.search(pattern, line, re.IGNORECASE):
            start = max(0, i - context_before)
            end = min(len(lines), i + context_after + 1)
            
            context = []
            for j in range(start, end):
                prefix = ">>>" if j == i else "   "
                context.append(f"{prefix} [Line {j+1:6d}] {lines[j]}")
            
            results.append('\n'.join(context))
    
    return results


def extract_error_lines(log_content, context_lines=3):
    """
    提取包含 error 关键词的行及其上下文
    """
    lines = log_content.split('\n')
    error_indices = set()
    
    error_keywords = [
        'error', 'ERROR', 'Error',
        'failed', 'FAILED', 'Failed',
        'fatal', 'FATAL', 'Fatal'
    ]
    
    for i, line in enumerate(lines):
        for keyword in error_keywords:
            if keyword in line:
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                error_indices.update(range(start, end))
                break
    
    error_indices = sorted(error_indices)
    
    if not error_indices:
        return [], []
    
    merged_ranges = []
    start = error_indices[0]
    end = error_indices[0]
    
    for idx in error_indices[1:]:
        if idx == end + 1:
            end = idx
        else:
            merged_ranges.append((start, end))
            start = idx
            end = idx
    merged_ranges.append((start, end))
    
    result_lines = []
    for start, end in merged_ranges:
        if result_lines:
            result_lines.append("..." + "=" * 70 + "...")
        for i in range(start, end + 1):
            result_lines.append(f"[Line {i+1:6d}] {lines[i]}")
    
    return result_lines, error_indices


def extract_last_lines(log_content, num_lines=500):
    """提取日志最后 N 行"""
    lines = log_content.split('\n')
    last_lines = lines[-num_lines:] if len(lines) > num_lines else lines
    
    result = []
    start_line = max(1, len(lines) - num_lines + 1)
    for i, line in enumerate(last_lines):
        result.append(f"[Line {start_line + i:6d}] {line}")
    
    return result


def main():
    # 解析参数
    args = sys.argv[1:]
    
    if not args or args[0].startswith('--'):
        print("用法: python fetch_gitlab_log.py <job_url> [options]")
        print("\n选项:")
        print("  --full           输出完整日志")
        print("  --tsan           提取 ThreadSanitizer 详细报告")
        print("  --search=PATTERN 搜索指定模式")
        print("\n示例:")
        print("  python fetch_gitlab_log.py https://gitlab.com/project/-/jobs/123456")
        print("  python fetch_gitlab_log.py https://gitlab.com/project/-/jobs/123456 --tsan")
        sys.exit(1)
    
    job_url = args[0]
    full_mode = '--full' in args
    tsan_mode = '--tsan' in args
    
    search_pattern = None
    for arg in args:
        if arg.startswith('--search='):
            search_pattern = arg.split('=', 1)[1]
    
    # 检查环境变量
    if not TOKEN:
        print("错误：未设置 GITLAB_TOKEN 环境变量")
        print("\n请先设置 token：")
        print("  export GITLAB_TOKEN='your_token_here'")
        sys.exit(1)
    
    try:
        # 解析 URL
        print(f"解析 job URL...", file=sys.stderr)
        gitlab_host, project_path, job_id = parse_job_url(job_url)
        
        print(f"项目: {project_path}", file=sys.stderr)
        print(f"Job ID: {job_id}", file=sys.stderr)
        
        # 获取日志
        print(f"\n正在获取日志...", file=sys.stderr)
        log_content = fetch_job_log(GITLAB_BASE_URL, project_path, job_id, TOKEN)
        
        total_lines = len(log_content.split('\n'))
        print(f"日志总行数: {total_lines}", file=sys.stderr)
        
        # 输出头部
        print("=" * 80)
        print("GitLab Job Log Analysis")
        print("=" * 80)
        print(f"Job URL: {job_url}")
        print(f"Total Lines: {total_lines}")
        
        # 根据模式输出
        if full_mode:
            print(f"Mode: FULL LOG")
            print("=" * 80)
            print(log_content)
            
        elif tsan_mode:
            print(f"Mode: THREAD SANITIZER ANALYSIS")
            print("=" * 80)
            
            summary_lines, detailed_issues = extract_tsan_reports(log_content)
            
            print(f"\n[TSAN SUMMARY] Found {len(summary_lines)} issues")
            print("-" * 80)
            for line in summary_lines:
                print(line)
            
            if detailed_issues:
                print(f"\n\n[TSAN DETAILED REPORTS] {len(detailed_issues)} issues")
                print("-" * 80)
                for i, issue in enumerate(detailed_issues[:10]):  # 最多显示10个详细报告
                    print(f"\n{'='*40} Issue {i+1} {'='*40}")
                    print(issue)
                
                if len(detailed_issues) > 10:
                    print(f"\n... (省略 {len(detailed_issues) - 10} 个 issues)")
            
        elif search_pattern:
            print(f"Mode: SEARCH PATTERN '{search_pattern}'")
            print("=" * 80)
            
            results = extract_pattern_context(log_content, search_pattern)
            print(f"\nFound {len(results)} matches")
            print("-" * 80)
            for i, result in enumerate(results[:50]):  # 最多显示50个结果
                print(f"\n--- Match {i+1} ---")
                print(result)
            
            if len(results) > 50:
                print(f"\n... (省略 {len(results) - 50} 个匹配)")
                
        else:
            # 默认模式：错误摘要 + 最后500行
            error_lines, error_indices = extract_error_lines(log_content)
            print(f"Error Lines Found: {len(error_indices)}")
            print("=" * 80)
            
            if len(error_lines) > 500:
                print("\n[ERROR CONTEXT] (前 500 行)")
                print("-" * 80)
                print('\n'.join(error_lines[:500]))
                print(f"\n... (省略 {len(error_lines) - 500} 行) ...")
            elif error_lines:
                print("\n[ERROR CONTEXT]")
                print("-" * 80)
                print('\n'.join(error_lines))
            else:
                print("\n[ERROR CONTEXT]")
                print("-" * 80)
                print("(未找到包含错误关键词的行)")
            
            print("\n\n" + "=" * 80)
            print("[LAST 500 LINES]")
            print("-" * 80)
            last_lines = extract_last_lines(log_content, 500)
            print('\n'.join(last_lines))
        
        print("=" * 80)
        
    except Exception as e:
        print(f"\n错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
