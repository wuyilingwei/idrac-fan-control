# iDRAC Fan Control

> 跨平台 Dell PowerEdge 风扇控制面板。通过 IPMI + Redfish 接管 iDRAC 风扇,支持温度曲线(阶梯/直线)自动调节、多服务器、开机自启、可配置通知。Linux 浏览器访问 / macOS·Windows 原生窗口。

[![tests](https://img.shields.io/badge/tests-197%20passed-success)](#) [![python](https://img.shields.io/badge/python-3.9%2B-blue)](#) [![iDRAC](https://img.shields.io/badge/iDRAC-7%20%7C%208%20%7C%209%20%7C%2010-informational)](#)

> Changelog: [v0.1.1](RELEASE_NOTES.md#v011) · [v0.1.0](RELEASE_NOTES.md#v010-—-initial-release)

---

## 特性

- **双后端**:IPMI raw(iDRAC ≤ 8 / iDRAC9 < 3.30.30.30)+ Redfish OEM(iDRAC9 ≥ 3.30.30.30 / iDRAC10)。能力探测自动路由,无需手动选择
- **温度曲线引擎**:`step`(阶梯)/ `linear`(直线)两种模式;前端可视化编辑器拖点 / 右键加点 / 双击删点
- **温度聚合策略**:`max`(最高)/ `avg`(平均);可指定参与传感器(为空 = 全部参与)
- **Failsafe(B 方案)**:超温阈值时仅告警 + 可选自动交还 Dell 控制(单一可开关兜底,不强制夺权)
- **通知**:Telegram + 通用 webhook,异步隔离 + 超时,失败不阻塞控制循环
- **HTTP API**:Starlette + Uvicorn,23+ 路由,核心服务 / GUI 分离,适配无头自启
- **前端**:Vue 3 + Vite + vue-i18n(中英文)+ 工科扁平面板风格,响应式 SVG 曲线编辑器
- **安全**:密码全 endpoint mask(前 3 后 2),可选环境变量驱动登陆鉴权,文件权限自动 600
- **打包**:PyInstaller 单文件,三平台自启脚本(systemd / LaunchAgent / 计划任务)

## 当前状态

代码层 M1–M7 全部完成,**197 mock 单测全过**;R730 真机已验证(IpmiBackend tick / set_fan_percent 持续工作)。

## 快速开始

```bash
# 1. 后端 + 前端依赖
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cd frontend && npm install && cd ..

# 2. 准备 config.json(参考 §配置)

# 3. 跑核心服务
.venv/bin/python -m app --config config.json --host 127.0.0.1 --port 8080

# 4. 浏览器访问
open http://localhost:8080
```

开发模式(前端 HMR):

```bash
# 终端 A:后端
.venv/bin/python -m app --config config.json

# 终端 B:vite dev(proxy /api/* → :8080)
cd frontend && npm run dev
# → http://localhost:5173
```

## 配置(`config.json`)

```jsonc
{
  "version": 2,
  "devices": [
    {
      "id": "r730-main",
      "name": "R730 主机",
      "host": "192.168.x.x",
      "user": "root",
      "password": "...",            // 明文,文件 chmod 600
      "backend": "ipmi",            // 能力探测会自动写
      "info": { "model": "...", "idrac_gen": 8, "idrac_firmware": "..." },
      "verify_tls": false,
      "temp_strategy": "max",       // max | avg
      "temp_sensors": []            // 参与传感器名(空 = 全部参与)
    }
  ],
  "curves": [
    {
      "id": "quiet", "name": "静音", "mode": "linear",
      "points": [{ "temp": 30, "pct": 15 }, { "temp": 80, "pct": 100 }]
    }
  ],
  "assignments": { "r730-main": "quiet" },
  "settings": {
    "failsafe_enabled": true,
    "failsafe_temp_c": 80,
    "poll_interval_s": 15,
    "autostart": false,
    "restore_on_exit": true,
    "language": "auto"
  },
  "notifiers": []
}
```

⚠️ **密码明文**:`config.json` 含 iDRAC 凭据,自动 `chmod 600`,**勿提交公开 git**(项目默认 `.gitignore` 已排除)。

## 登陆鉴权(可选 · v0.1.1+)

主密码在 **Settings → 鉴权与监听** 中设置,存 `config.json.settings.master_password`。

- **未设主密码**(默认):服务**强制只监听 127.0.0.1**(只有本机能访问)+ 无鉴权直接进。Settings 中 `bind_host` 输入框锁定。
- **设了主密码**:Settings 中 `bind_host` 解锁,可改成 `0.0.0.0` 或具体网卡 IP(改完重启生效)。所有 API 走 Bearer token 鉴权。

Token 进程级 in-memory,重启失效;清密码 = 即刻关闭鉴权。

## 温度策略(两层组合)

| `temp_strategy` | `temp_sensors` | 行为 |
|---|---|---|
| `max` | `[]` | 所有温度传感器中取最高 |
| `max` | `["Inlet Temp", "CPU1"]` | 仅这两个之间取最高 |
| `avg` | `[]` | 所有传感器平均 |
| `avg` | `["Exhaust Temp", "CPU1"]` | 这两个的平均 |

R730 实测可选传感器:`Inlet Temp` / `Exhaust Temp` / `Temp`(CPU1)/ `Temp`(CPU2)。

## HTTP API 速览

```
GET   /api/health
GET   /api/config                                整体配置
PUT   /api/config
GET   /api/devices                               设备列表(密码 mask)
POST  /api/devices
GET   /api/devices/{id}
PUT   /api/devices/{id}                          PUT 时回传 mask 占位 → 沿用旧密码
DELETE /api/devices/{id}
GET   /api/devices/{id}/sensors                  真传感器列表(供策略选择)
POST  /api/devices/{id}/fan/manual  {"pct": 30}  手动转速
POST  /api/devices/{id}/fan/auto                 交还 Dell 自动
POST  /api/devices/{id}/probe                    能力探测
GET/POST /api/curves
GET/PUT/DELETE /api/curves/{id}
GET   /api/assignments
PUT   /api/assignments/{device_id}  {"curve_id": "..."}    null 移除
GET/PUT /api/settings
GET   /api/status                                最近一次 tick 结果
POST  /api/notifiers/test                        测试发送
GET   /api/auth/status                           是否要求登陆
POST  /api/auth/login                            {"password": "..."} → token
POST  /api/auth/logout
```

## 测试

```bash
.venv/bin/pytest test/ --ignore=test/m1_ipmi/test_ipmi_integration.py --ignore=test/m2_config/test_probe_integration.py -q
# → 197 passed
```

集成测试需要真机 R730 凭据,放 `agents/test-target.json`(gitignored)。

## 项目结构

```
idrac-fan-control/
├── app/
│   ├── __main__.py            # 无头入口 (python -m app)
│   ├── desktop.py             # pywebview 桌面入口
│   ├── main.py                # Starlette API + 路由
│   ├── service.py             # ServiceContainer + 后台 tick
│   ├── config.py              # config.json schema + dataclass
│   ├── engine.py              # ControlLoop + Backend Protocol + failsafe
│   ├── curve.py               # evaluate_curve (step/linear)
│   ├── notify.py              # telegram + webhook
│   ├── idrac/
│   │   ├── ipmi.py            # pyghmi 后端(R730 主路径)
│   │   ├── redfish.py         # httpx 客户端 + redfish_oem 控制(TODO)
│   │   ├── backends.py        # IpmiBackend(M3 Protocol 实现)
│   │   └── probe.py           # 能力探测 + host_os
│   ├── cli/
│   │   ├── m1_verify.py       # IPMI 主链路 CLI
│   │   ├── m2_probe.py        # probe / dump-default CLI
│   │   └── m3_simulate.py     # 曲线模拟 CLI
│   └── static/                # ← Vue build 产物
├── frontend/
│   ├── src/
│   │   ├── App.vue            # 全局 CSS(工科风格)
│   │   ├── api.js
│   │   ├── components/{CurveEditor,Login}.vue
│   │   ├── views/{Status,Devices,Curves,Settings,Notifiers}View.vue
│   │   └── locales/{zh-CN,en}.json
│   └── vite.config.js
├── test/                      # 197 mock 单测 + 集成测试 skipif
├── scripts/install/{linux,macos,windows}/  # 三平台自启脚本
├── build.spec                 # PyInstaller 单文件
├── PLAN.md                    # 完整设计文档 v2
└── README.md                  # 本文件
```

## 打包 / 自启(三平台)

```bash
# 1. 前端 build
cd frontend && npm run build && cd ..   # → app/static/*

# 2. PyInstaller
pip install pyinstaller
pyinstaller build.spec                  # → dist/idrac-fan-control

# 3. 三平台自启
bash scripts/install/linux/install.sh /opt/idrac-fan-control          # systemd --user
bash scripts/install/macos/install.sh /opt/idrac-fan-control          # LaunchAgent + 自动解 quarantine
powershell scripts\install\windows\install-task.ps1 -InstallDir ...   # 计划任务
```

详见 [`scripts/install/README.md`](scripts/install/README.md)。

## 已知限制

- ⚠️ **iDRAC9+ redfish_oem 控制路径**未在真机验证(目标机只有 iDRAC8 R730);代码骨架就绪,字段 `# TODO: 待 iDRAC9+ 真机验证`
- ⚠️ **iDRAC8 Probe 拿 host OS** 极慢且大概率失败(Redfish 不暴露);需在 host 装 Dell iSM 服务后才有 `DellSystem.HostOSName` 字段
- ⚠️ **macOS 不签名**,LaunchAgent 启动可能被 Gatekeeper 拦,install.sh 自动 `xattr -d com.apple.quarantine`

## 设计文档

完整设计、决策、参考代码、风险清单见 [PLAN.md](PLAN.md)。

## 许可

MIT(见 [LICENSE](LICENSE))。

## 致谢

- 设计参考:[tigerblue77/Dell_iDRAC_fan_controller_Docker](https://github.com/tigerblue77/Dell_iDRAC_fan_controller_Docker) · [kuan909608/dell-idrac-fan-controller-gpu](https://github.com/kuan909608/dell-idrac-fan-controller-gpu)
- Dell 官方:[iDRAC-Redfish-Scripting](https://github.com/dell/iDRAC-Redfish-Scripting) · [OMSDK](https://github.com/Dell/omsdk)
- 协议库:[pyghmi](https://opendev.org/x/pyghmi) · [httpx](https://www.python-httpx.org) · [Starlette](https://www.starlette.io) · [Vue 3](https://vuejs.org) · [vue-i18n](https://vue-i18n.intlify.dev) · [pywebview](https://pywebview.flowrl.com)
