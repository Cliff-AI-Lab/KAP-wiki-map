---
title: KAP 项目推送到 GitHub 标准流程
skill-name: kap-github-push
triggers:
  - "推到 github"
  - "push 到 github"
  - "推送到远程"
  - "上传 github"
created: 2026-05-16
source-context: M22 #8 后首次成功 push 到 Cliff-AI-Lab/KAP-wiki-map
---

# KAP 项目推送到 GitHub 标准流程

> 本文是 KAP 项目首次 push 到 `Cliff-AI-Lab/KAP-wiki-map.git` 时踩坑沉淀的可复用流程。下次 Claude 会话遇到"推到 github" 等触发词时直接按本流程走。

## 0. 关键约束（不可违反）

1. **绝不 force push main**（system prompt 安全协议）
2. **绝不改 git config**（KAP 用 env vars 注入身份，见 [memory: reference_kap_git_identity](../../memory/reference_kap_git_identity.md)）
   - 每次涉及创建 commit 的操作（包括 rebase）必须设 `GIT_AUTHOR_NAME=KAP GIT_AUTHOR_EMAIL=kap@local GIT_COMMITTER_NAME=KAP GIT_COMMITTER_EMAIL=kap@local`
3. **绝不让 secret 进 git**（`backend/configs/llm_settings.json` 含真实 API Key，.gitignore 隔离）
4. **rebase 重写 hash 是不可逆操作**（reflog 可救但 hash 全变），动手前用户必须明确授权

## 1. Pre-flight 安全检查

```bash
cd "E:/Obsidian/知识PPL/raw/KAP知识智能体平台"

# 1.1 远程配置
git remote -v
# 期望: origin git@github.com:Cliff-AI-Lab/KAP-wiki-map.git
# 或   origin https://github.com/Cliff-AI-Lab/KAP-wiki-map.git

# 1.2 当前 HEAD
git rev-parse HEAD
HEAD_BEFORE=$(git rev-parse HEAD)

# 1.3 工作区是否有未提交修改
git status --short
# 关注 dirty 文件（特别是 backend/configs/llm_settings.json 是否泄露）

# 1.4 reflog 看是否曾经 push 过
git reflog --all | grep -iE "push|fetch" | head -5
# 0 条 → 首次 push, 远程可能有 GitHub 自动 Initial commit
```

## 2. 认证路径选择

KAP 项目首次 push 时实测：**HTTPS + GCM 比 SSH 稳**。

### 2.1 先试 SSH（如果之前能通）

```bash
ssh -T git@github.com 2>&1 | tail -3
# 通: "Hi <user>! You've successfully authenticated..."
# 不通: "Permission denied (publickey)" → 走 2.2
```

**SSH 不通的常见原因**：
- 本机 SSH key (`~/.ssh/id_ed25519` 或 `~/.ssh/id_rsa`) 公钥指纹未注册在能访问该仓库的 GitHub 账号
- Cliff-AI-Lab 是 Organization 仓库 → key 未给 org SSO 授权
- ssh-agent 没加载 key（`ssh-add -l` 失败）

### 2.2 用 HTTPS + GCM（Windows 推荐）

```bash
# Windows GCM 已配置时（git config --get credential.helper 返回 manager）：
git remote set-url origin https://github.com/Cliff-AI-Lab/KAP-wiki-map.git
git ls-remote origin 2>&1 | head -5
# 通: 返回远程 refs/heads/main 的 hash
# 不通: 弹浏览器登录窗（首次）→ 授权后凭据自动缓存到 Windows Credential Manager
```

**GCM 优势**：跨仓库共享凭据。**只要这台 Windows 之前用 HTTPS push 过任何 GitHub 仓库，立即生效**。

### 2.3 验证网络可达性（push 失败时）

```bash
curl -s -o /dev/null -w "github.com:443 status=%{http_code} time=%{time_total}\n" --max-time 10 https://github.com
# status=000 + time=10s → 网络层不通（可能 v2rayN/代理状态变化，等几秒重试）
# status=200 → 网络通, 错误是认证/git 协议层
```

## 3. 远程仓库状态判断

```bash
git fetch origin
git log --oneline origin/main -3
```

三种情形：
- **空仓库**（remote/main 不存在）：可直接 `git push -u origin main`
- **有 Initial commit (LICENSE/README)**：本地与远程**不共享历史** → 必须 rebase 或 force（走 §4）
- **远程有真实 commit**：先 `git pull --rebase`，处理冲突，再 push

## 4. Rebase 整合远程 Initial commit（KAP 实测路径）

如果远程只有 GitHub 自动 `Initial commit` (LICENSE)，本地 N 个 commit 与之不共享历史：

### 4.1 备份 secret 文件（防 rebase 冲突）

```bash
# M22 #8 实测坑: backend/configs/llm_settings.json 是 untracked,
# 但 M0 Day 0 commit 当时它是 tracked, rebase replay M0 时会冲突
if [ -f backend/configs/llm_settings.json ]; then
    cp backend/configs/llm_settings.json /tmp/llm_settings.json.backup
    rm backend/configs/llm_settings.json
    echo "secret backed up to /tmp"
fi
```

### 4.2 用 env vars 注入身份做 rebase（**关键**）

```bash
GIT_AUTHOR_NAME=KAP GIT_AUTHOR_EMAIL=kap@local \
GIT_COMMITTER_NAME=KAP GIT_COMMITTER_EMAIL=kap@local \
git rebase origin/main
# 期望输出: Rebasing (1/N)Rebasing (2/N)...Successfully rebased and updated refs/heads/main.
```

**没设 env vars 会怎样**：rebase 在 commit 1 就报 `Committer identity unknown` 失败，留下 `.git/rebase-merge/` 中间状态。

### 4.3 还原 secret 文件

```bash
if [ -f /tmp/llm_settings.json.backup ]; then
    cp /tmp/llm_settings.json.backup backend/configs/llm_settings.json
    rm /tmp/llm_settings.json.backup
fi
git status --ignored backend/configs/ | grep "!!"
# 期望: !! backend/configs/llm_settings.json （仍被 .gitignore 忽略）
```

## 5. Push

```bash
git push -u origin main 2>&1 | tail -5
```

**push 时网络抖动**：见过 `Failed to connect to github.com port 443 after 21079 ms`。等几秒 + 验证 `curl https://github.com` + 重试。**绝不因为偶发网络失败改成 force push**。

## 6. 应急：rebase 中途崩了怎么办

```bash
# 6.1 看状态
ls .git/ | grep -iE "rebase|merge|lock"

# 6.2 完整清理
git rebase --abort 2>&1
rm -f .git/index.lock
rm -rf .git/rebase-merge .git/rebase-apply

# 6.3 工作树还原（reflog 安全恢复点）
git reflog -5  # 找到 rebase 前的 commit hash
git reset --hard $HEAD_BEFORE  # 用 pre-flight 时保存的 hash

# 6.4 确认干净
git status --short
# 仅 untracked 文件 (.claude/ 等) 算正常
```

## 7. 打包对齐的 zip（push 后）

rebase 重写了本地 commit hash，旧 zip 文件名里的 hash 已对不上 GitHub。重新打：

```bash
NEW_HASH=$(git rev-parse --short HEAD)
TS=$(date +%Y%m%d-%H%M)
git archive --format=zip \
    --output="E:/Obsidian/知识PPL/raw/KAP-source-${TS}-${NEW_HASH}.zip" \
    --prefix=KAP/ HEAD

# 验证内容
python -c "import zipfile; z=zipfile.ZipFile('E:/Obsidian/知识PPL/raw/KAP-source-'+'${TS}'+'-'+'${NEW_HASH}'+'.zip'); print('files:', len(z.namelist())); print('size:', __import__('os').path.getsize(z.filename))"
```

**git archive 优势**：只含 tracked 文件 + 自动遵守 .gitignore → secret 永不入 zip。

## 8. 实测踩坑总结（2026-05-16 M22 #8 push）

| 坑 | 表现 | 根因 | 解 |
|:---|:---|:---|:---|
| SSH 不通 | `Permission denied (publickey)` 两次（本机两个 key 都试过）| GitHub 账号未注册这些公钥指纹 | 走 HTTPS + GCM 路径 |
| 网络抖动 | `Failed to connect to github.com port 443` | github.com:443 偶发不通（api.github.com 通），可能代理软件状态 | 等几秒重试，绝不 force push |
| Rebase 冲突 | `untracked working tree files would be overwritten` | 本地 untracked `llm_settings.json` 与 M0 Day 0 当时 tracked 同名文件 | 备份到 /tmp + rm 后 rebase + 还原 |
| Rebase committer | `Committer identity unknown` | KAP 不改 git config（memory 约束），rebase 时缺 user.email | 4 个 env vars 注入：`GIT_AUTHOR_* + GIT_COMMITTER_*` |
| .git 状态混乱 | `index.lock`/`rebase-merge` 残留导致后续命令拒绝 | abort 在 Windows + msys 偶发不完整 | `rm -f .git/index.lock && rm -rf .git/rebase-merge` 强清后 reset --hard |

## 9. 当本 skill 不适用

- **你不是 KAP 项目**：流程的"env vars 注入身份"/"secret 隔离"是 KAP 特有约定
- **你之前已经 push 过同一个仓库**：远程历史可能复杂，不一定能简单 rebase
- **远程不是 GitHub**（GitLab / Gitee）：HTTPS 凭据机制不一样

---

> **触发本 skill**：用户说"推到 github"/"push 到 github"/"上传 github"等时，Claude 应自动加载本文档作为参考，按步骤执行。
> **维护**：发现新的坑请追加到 §8 表格。
