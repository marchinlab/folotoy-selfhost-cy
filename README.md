# 火火兔-CY定制版

基于火火兔（FoloToy）自建服务端的定制版本，加入联网问答、粤语角色、定时播报与电台推送能力。本项目为脱敏发布版，仅含核心代码与配置模板，不含任何真实密钥、设备序列号或个人网络信息。

## 功能概览

- **本地语音助手**：STT（语音转写）→ LLM（大模型回答）→ TTS（语音合成）全链路自建
- **多角色设定**：7 个功能键对应不同学科/闲聊角色，支持粤语个性化人设
- **联网增强**：新闻、天气、百科查询与主动定时播报
- **电台推送**：把网络电台录成片段，经 MQTT 推送到火火兔播放，支持连续播放与看门狗自愈
- **Docker 部署**：服务端组件容器化，一键启动

## 目录结构

```
.
├── docker-compose.yml        容器编排（网关 / STT / EMQX / nginx 等）
├── .env.example              环境变量模板（复制为 .env 后填写）
├── .env.free.example         免费方案模板
├── config/roles.json         角色配置（人设、音色、模型）
├── gateway/                  LLM 网关、播报、按键控制、部署脚本
├── clawbot_to_folotoy.py     ClawBot / 手表电台到火火兔的桥接
├── radio_loop.py             电台连续播放循环
├── radio_watchdog.py         电台看门狗（自愈假死/假活/睡眠冻结）
├── radio_cmd_bridge.py       电台命令桥接
├── *_说明.md                  角色与配置说明文档
└── *.bat / *.ps1             Windows 侧一键脚本
```

## 快速开始

### 1. 环境要求

- Linux / WSL2 主机（推荐 Ubuntu 22.04）
- Docker 与 Docker Compose
- 火火兔设备与主机在同一局域网

### 2. 配置

```bash
cp .env.example .env
# 编辑 .env：填写 LLM_API_KEY、STT_API_KEY、PUBLIC_HOST 等
```

关键配置：

| 变量 | 说明 |
|------|------|
| `PUBLIC_HOST` | 服务端 IP 或域名（不要带 http:// 和端口） |
| `LLM_API_BASE` / `LLM_API_KEY` | OpenAI 兼容的大模型接口 |
| `LLM_MODEL` | 必须与 `config/roles.json` 中的 `model` 一致 |
| `STT_TYPE` / `STT_API_BASE` / `STT_API_KEY` | 语音转写服务 |
| `TTS_TYPE` | 语音合成，默认 `edge-tts`（免费） |
| `MQTT_PASSWORD` | 服务端连 EMQX 的密码 |

> 想零成本试用：直接用 `.env.free.example`，用同一个硅基流动 Key 搞定听、想、说。

### 3. 启动

```bash
docker compose up -d
```

### 4. 电台功能（可选）

Windows 侧运行 `radio-play.bat` 开始连续播放，`radio-stop.bat` 暂停。看门狗脚本 `radio_watchdog.py` 可注册为计划任务自动自愈。详见源码注释。

## 安全与脱敏说明

- 本仓库已移除所有真实 API Key、Wi-Fi 名称与密码、设备序列号、内网 IP、个人用户名与路径、GitHub 账号信息。
- 真实密钥统一用 `sk-REDACTED`、`YOUR_*` 等占位符替代，部署时自行填写。
- `.gitignore` 已排除 `.env`、日志、音频、锁文件与备份。
- **风险提示**：本项目涉及公网暴露的语音服务，生产部署务必：改掉默认 MQTT 密码、限制端口访问、不要在公开网络使用弱口令。
- 若你发现任何遗漏的敏感信息，请立即通过 Issue 告知维护者。

## 免责声明

本项目为个人定制与学习用途，与火火兔官方（FoloToy）无关联。使用第三方大模型与语音服务产生的费用与合规责任由使用者自行承担。
