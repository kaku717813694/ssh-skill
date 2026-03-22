---
name: ssh-skill
version: 3.2.1-codex
description: "CRITICAL: Use this skill for all SSH operations in Codex. Covers remote servers, jump hosts, bastions, routers, switches, firewalls, uploads, downloads, and server-to-server transfer. In the current Codex environment on Windows, prefer PowerShell + `py -3` + `$HOME/.codex/skills/ssh-skill/scripts`. Do not use raw `ssh`/`scp` unless you are explicitly bootstrapping keys or this skill is unavailable."
keywords: SSH,服务器,远程,连接,命令,上传,下载,文件传输,跳板机,批量,集群,deploy,部署,运维,登录,执行,查看,检查,管理,操作,访问,传输,迁移,服务器间,华为,H3C,飞塔,FortiGate,交换机,路由器,防火墙
---

# SSH Skill for Codex

面向 Codex 的 SSH 操作技能。

核心目标：
- 所有 SSH 操作统一走本 skill 的脚本
- 优先使用别名而不是裸 IP + 临时命令
- 在当前 Windows + PowerShell + Codex 环境里给出可直接执行的命令
- 兼容服务器与网络设备（华为、H3C、FortiGate / 飞塔等）

## 何时使用

以下场景都必须优先使用本 skill：
- 登录远程服务器、网络设备、跳板机、堡垒机
- 执行远程命令
- 上传、下载、服务器间传输文件
- 批量巡检、批量执行命令
- 维护 SSH 别名、标签、环境、位置等配置

不要用于：
- 本地命令
- `localhost`
- 当前工作目录内的普通文件操作

## 当前环境约定

当前主环境是：
- 宿主：Codex
- Shell：PowerShell
- Skill 根目录：`$HOME/.codex/skills/ssh-skill/scripts`
- Windows 解释器优先级：`py -3` > `python`

如果未来运行在其他宿主中：
- Codex 默认路径：`$HOME/.codex/skills/ssh-skill/scripts`
- Claude 类宿主若确实安装在 `.claude`，再改为：`$HOME/.claude/skills/ssh-skill/scripts`

## 调用规则

### 唯一正确方式

在当前 Windows + PowerShell + Codex 环境中，优先使用：

```powershell
py -3 "$HOME/.codex/skills/ssh-skill/scripts/脚本名.py" ...
```

如果是在 Linux / macOS Bash 环境，可改为：

```bash
python3 "$HOME/.codex/skills/ssh-skill/scripts/脚本名.py" ...
```

禁止做法：
- 不要直接写 `ssh` 或 `scp`
- 不要把 `~/.claude/...` 当成当前默认路径
- 不要在 PowerShell 里使用 `MSYS_NO_PATHCONV=1 python ...` 这种 Bash 写法
- 不要先 `cd` 到脚本目录再执行

### PowerShell 下设置 `MSYS_NO_PATHCONV`

上传、下载、服务器间传输在 Windows 下仍然建议带 `MSYS_NO_PATHCONV`，
但 PowerShell 写法必须是：

```powershell
$env:MSYS_NO_PATHCONV = '1'
py -3 "$HOME/.codex/skills/ssh-skill/scripts/脚本名.py" ...
```

不要写成：

```bash
MSYS_NO_PATHCONV=1 python ...
```

## 常用命令

### 列出服务器

```powershell
py -3 "$HOME/.codex/skills/ssh-skill/scripts/ssh_config_manager_v3.py" list-servers
```

### 查找服务器

```powershell
py -3 "$HOME/.codex/skills/ssh-skill/scripts/ssh_config_manager_v3.py" find "<关键词>"
```

### 执行远程命令

```powershell
py -3 "$HOME/.codex/skills/ssh-skill/scripts/ssh_execute.py" <别名> "<命令>"
```

可选参数：`--timeout <秒>` `--no-daemon`

### 上传文件

```powershell
$env:MSYS_NO_PATHCONV = '1'
py -3 "$HOME/.codex/skills/ssh-skill/scripts/ssh_upload.py" <别名> "<本地路径>" "<远程路径>"
```

可选参数：`--resume` `--recursive` `--no-progress`

### 下载文件

```powershell
$env:MSYS_NO_PATHCONV = '1'
py -3 "$HOME/.codex/skills/ssh-skill/scripts/ssh_download.py" <别名> "<远程路径>" "<本地路径>"
```

可选参数：`--resume` `--recursive` `--no-progress`

### 服务器间传输

```powershell
$env:MSYS_NO_PATHCONV = '1'
py -3 "$HOME/.codex/skills/ssh-skill/scripts/ssh_server_transfer.py" <源别名> "<源路径>" <目标别名> "<目标路径>"
```

可选参数：
- `--mode <auto|direct|stream|hybrid>`
- `--use-rsync`
- `--no-progress`
- `--size-threshold <MB>`
- `--timeout <秒>`

### 批量执行

```powershell
py -3 "$HOME/.codex/skills/ssh-skill/scripts/ssh_cluster.py" "<命令>" --parallel
```

常用过滤：
- `--hosts "DEV-002,DEV-003"`
- `--environment production`
- `--tags "web,nginx"`

### 管理守护进程

```powershell
py -3 "$HOME/.codex/skills/ssh-skill/scripts/ssh_daemon.py" start <别名>
py -3 "$HOME/.codex/skills/ssh-skill/scripts/ssh_daemon.py" status <别名>
py -3 "$HOME/.codex/skills/ssh-skill/scripts/ssh_daemon.py" stop <别名>
```

## 配置管理

配置文件位置：
- `~/.ssh/config`

常用命令：

```powershell
py -3 "$HOME/.codex/skills/ssh-skill/scripts/ssh_config_manager_v3.py" create --alias <别名> --host <IP> --user <用户名> --key <密钥文件> --environment <环境>
py -3 "$HOME/.codex/skills/ssh-skill/scripts/ssh_config_manager_v3.py" update <别名> --description "新描述"
py -3 "$HOME/.codex/skills/ssh-skill/scripts/ssh_config_manager_v3.py" delete <别名>
```

推荐做法：
- 用别名管理设备，不要每次手写 IP
- 用 `tags` 标记类型，例如：`network,h3c,access-switch`
- 用 `environment` 标记环境，例如：`production`
- 用 `location` 标记机房或楼层

## 网络设备专项约定

本 skill 可以直接用于：
- 华为路由器、交换机
- H3C 交换机
- FortiGate / 飞塔防火墙
- 其他支持 SSH 的网络设备

但它本质上仍然是通用 SSH 框架，不会自动识别厂商 CLI 差异。

处理网络设备时建议：
- 华为 / H3C 这类会话级设备，可先发禁分页命令再采集
- FortiGate 默认保持只读，不自动改 console 配置
- 优先执行只读巡检命令
- 避免直接下配置变更，除非用户明确要求
- 对多设备批量巡检时，优先通过标签筛选

常见禁分页示例：

```text
华为：screen-length 0 temporary
H3C：screen-length disable

FortiGate 说明：
- 不默认自动执行 `config system console -> set output standard`
- 因为这属于配置模式变更，不适合作为巡检前的隐式动作
- 如确实需要，必须在用户明确接受后手工执行
```

如果不确定厂商命令：
- 先执行只读探测命令确认设备类型
- 再执行对应厂商命令

## 守护进程说明

守护进程主要用于密码认证场景，加速重复执行：
- 首次连接自动启动
- 后续可复用长连接
- 空闲 30 分钟自动退出

多个 Codex / Claude 类会话可以复用同一守护进程。

## 输出格式

脚本默认输出 JSON，适合后续解析：

```json
{
  "success": true,
  "exit_code": 0,
  "stdout": "命令输出",
  "stderr": ""
}
```

## 故障排查

### 命令找不到

优先检查：
- 当前是否在 Windows PowerShell
- 是否使用了 `py -3`
- 路径是否指向 `$HOME/.codex/skills/ssh-skill/scripts`

### 别名不存在

```powershell
py -3 "$HOME/.codex/skills/ssh-skill/scripts/ssh_config_manager_v3.py" find "<关键词>"
```

### 守护进程异常

```powershell
py -3 "$HOME/.codex/skills/ssh-skill/scripts/ssh_daemon.py" stop <别名>
py -3 "$HOME/.codex/skills/ssh-skill/scripts/ssh_execute.py" <别名> "<命令>" --no-daemon
```

### 路径被错误转换

上传、下载、服务器间传输前，在 PowerShell 下先设置：

```powershell
$env:MSYS_NO_PATHCONV = '1'
```

## 强制规则

- 所有 SSH 操作优先走本 skill
- 当前 Codex 环境默认路径是 `.codex`，不是 `.claude`
- 当前 Windows 环境优先用 `py -3`
- 远程设备优先用别名，不要裸写账号密码
- 多个只读巡检命令可合并为一次执行
- 涉及批量变更、配置下发、删除文件、重启服务等高风险动作前，必须先明确用户意图
