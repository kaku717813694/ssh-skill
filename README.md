# SSH Skill for Codex

面向 Codex 的 SSH skill，统一处理服务器和网络设备的远程执行、传输和批量操作。

这个分支额外补强了网络设备交互式 shell，当前已经覆盖：

- Linux / Unix 服务器
- 跳板机 / Bastion / ProxyJump
- 上传、下载、服务器间传输
- 批量并发执行
- 华为、H3C、FortiGate 等 SSH 网络设备

当前推荐环境：

- Windows
- PowerShell
- `py -3`
- `$HOME/.codex/skills/ssh-skill/scripts`

## What This Skill Supports

### Server operations

- 远程执行命令
- 复用守护进程长连接
- 上传、下载、断点续传
- 服务器到服务器直传
- 基于 `~/.ssh/config` 的别名管理

### Network device operations

- 自动识别部分网络设备目标并切到 shell 模式
- 按厂商加载 prompt、分页、错误识别规则
- 支持多命令拆分执行
- 支持分页提示和确认提示自动应答
- 支持只读巡检优先的默认策略

当前内置厂商 profile：

- Huawei
- H3C
- FortiGate
- Cisco
- Arista
- Juniper

## Install

1. 安装 Python 依赖：

```powershell
py -3 -m pip install paramiko
```

2. 把仓库放到 Codex skill 目录：

```text
$HOME/.codex/skills/ssh-skill
```

3. 在 `~/.ssh/config` 中准备好主机别名、账号和跳板机配置。

4. 在 Codex 中使用自然语言触发 SSH 场景，或直接运行脚本。

## Quick Start

### Execute on a server

```powershell
py -3 "$HOME/.codex/skills/ssh-skill/scripts/ssh_execute.py" prod-web-01 "systemctl status nginx"
```

### Upload a file

```powershell
$env:MSYS_NO_PATHCONV = '1'
py -3 "$HOME/.codex/skills/ssh-skill/scripts/ssh_upload.py" prod-web-01 ".\\app.tar.gz" "/tmp/app.tar.gz"
```

### Download a file

```powershell
$env:MSYS_NO_PATHCONV = '1'
py -3 "$HOME/.codex/skills/ssh-skill/scripts/ssh_download.py" prod-web-01 "/var/log/nginx/access.log" ".\\access.log"
```

### Transfer server to server

```powershell
$env:MSYS_NO_PATHCONV = '1'
py -3 "$HOME/.codex/skills/ssh-skill/scripts/ssh_server_transfer.py" old-server "/data/backup.tar.gz" new-server "/backup/"
```

### Run on multiple hosts

```powershell
py -3 "$HOME/.codex/skills/ssh-skill/scripts/ssh_cluster.py" "df -h" --environment production --parallel
```

## Network Device Usage

`ssh_execute.py` 现在支持三种模式：

- `--mode exec`：按传统服务器命令执行
- `--mode shell`：强制走交互式 shell
- `--mode auto`：根据别名和元数据自动判断

### Huawei

```powershell
py -3 "$HOME/.codex/skills/ssh-skill/scripts/ssh_execute.py" core-sw-01 "display version;;display lldp neighbor brief"
```

默认会发送会话级禁分页命令：

```text
screen-length 0 temporary
```

### H3C

```powershell
py -3 "$HOME/.codex/skills/ssh-skill/scripts/ssh_execute.py" access-sw-07 "display version;;display interface brief"
```

默认会发送会话级禁分页命令：

```text
screen-length disable
```

### FortiGate

```powershell
py -3 "$HOME/.codex/skills/ssh-skill/scripts/ssh_execute.py" edge-fgt-01 "get system status"
```

FortiGate 当前默认保持只读优先：

- 不自动执行 `config system console`
- 不自动执行 `set output standard`
- 不隐式修改 console / paging 配置

这意味着它更适合默认巡检，不会在“读状态”前先改设备配置。

### Shortcuts

已定义的快捷命令只在对应厂商下生效：

- Huawei / H3C：`@uptime`、`@version`
- FortiGate：`@status`、`@ha`、`@version`

未定义的快捷命令现在会在本地直接报错，不再透传到设备。

## Safety Defaults

这条分支刻意收紧了几个高风险点：

- FortiGate 默认不改配置，只做只读命令
- 未知网络设备 shortcut 本地直接拒绝
- 分页 `more` 匹配已收紧，避免普通输出误触发翻页
- Obsidian 密码回退只有在显式环境变量开启时才生效

如果要执行配置变更，建议显式使用：

- `--mode shell`
- `--config-mode`
- `--save`

并在执行前确认命令确实会改配置。

## SSH Config Notes

这个 skill 继续基于标准 `~/.ssh/config` 工作，建议优先维护别名，不要在命令里重复写裸 IP。

示例：

```ssh-config
Host core-sw-01
    HostName 10.1.1.2
    User admin

Host edge-fgt-01
    HostName 10.1.1.1
    User admin

Host app-prod-01
    HostName 10.10.10.21
    User root
    ProxyJump bastion-01
```

## Validation

当前分支已完成的验证：

- 单元测试：`20 passed, 2 skipped`
- 2026-03-22 真机只读验证通过
- 华为设备：`display version`、`display lldp neighbor brief`
- H3C 设备：`display version`、`display interface brief`
- FortiGate：`get system status`

真机验证结论：

- 华为 / H3C 的会话级禁分页正常
- FortiGate prompt 识别正常
- FortiGate 默认不会再自动修改 console 配置

## Branch Status

这些网络设备增强当前位于：

```text
feat/network-device-shell
```

不是 `main`。

如果你要在 GitHub 上看这版能力，请看这个分支，而不是默认分支。

## License

MIT
