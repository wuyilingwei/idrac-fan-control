# v0.1.1 — Auth & Bind safety + logo

> 2026-06-15(本地)

## 🔐 安全默认

- 主密码移到 `settings.master_password`(从环境变量 IDRAC_AUTH_PASSWORD 改)
- 默认无主密码 → 启动强制 bind 127.0.0.1
- Settings UI 新增"鉴权与监听"段:密码字段 + bind_host + 警告;无密码时 bind_host 锁定
- AuthMiddleware 动态读 settings(改完无需重启即生效;bind_host 改需重启)

## 🎨 UI

- 新 logo:圆形蓝底白叶风扇 + 12 道温度刻度环;同时作 favicon + header brand

## 🛠 Tests

- 197 mock 单测仍过(M2 settings 字段断言已更新)

---

# v0.1.0 — Initial Release

> 2026-06-15 · commit `a04b342`

iDRAC Fan Control 首个公开版本。代码层 M1–M7 全部完成,**197 mock 单测全过**,R730 真机已持续验证(IpmiBackend tick + set_fan_percent 稳定)。

## ✨ Highlights

| 模块 | 实现 |
|---|---|
| **双后端路由** | IPMI raw(iDRAC ≤ 8 / iDRAC9 < 3.30.30.30)+ Redfish OEM(iDRAC9 ≥ 3.30.30.30 / iDRAC10);能力探测自动判 |
| **温度曲线** | `step` / `linear` 两种;前端 SVG 编辑器自适应宽度 + 圆点保持圆形 + 右键加点 / 双击删点 / 拖动跟随鼠标(约束在前后两点之间)|
| **温度策略** | 两层正交:`max` / `avg` 聚合方法 × `temp_sensors`(空=全部 / 选中=只算这些) |
| **failsafe(B 方案)** | 单一可开关兜底:超温触发告警,可选自动交还 Dell 自动控制(不强制夺权) |
| **通知** | Telegram + 通用 webhook;异步 fire-and-forget + 超时;失败仅 log,绝不阻塞主控制循环 |
| **HTTP API** | Starlette 23 路由;ServiceContainer + lifespan;核心服务 / GUI 分离(无头自启就绪) |
| **前端** | Vue 3 + Vite + vue-i18n(zh-CN / en);工科扁平面板风格;ResizeObserver 响应式 SVG |
| **安全** | 密码全 endpoint mask `前3***后2`;PUT 时 mask 占位 → 沿用旧密码;可选 env 主密码登陆(token in-memory);config.json chmod 600;agents/ 工作流目录排除 git |
| **打包** | PyInstaller 单文件 + Linux systemd / macOS LaunchAgent / Windows 计划任务三平台自启脚本 |

## 📦 Production Build

`frontend/` 已构建并产物落 `app/static/`:

```
app/static/index.html                   0.83 kB
app/static/assets/index-CRh3-daC.css   11.27 kB  gzip 2.75 kB
app/static/assets/index-BXBLZoNt.js   152.54 kB  gzip 55.24 kB
```

启动:`.venv/bin/python -m app --config config.json --host 127.0.0.1 --port 8080` → 浏览器 http://localhost:8080

## 🧪 Verified

- **Mock 单测**:197 passed in 0.34s(M1·22 / M2·47 / M3·56 / M4·19 / M5·40 / M7·13)
- **R730 真机**:`temp 47.0 °C → target_pct 5 (quiet linear) / status: ok`,15+ 分钟持续稳定;`keepalive=False` + cached single session 解决 iDRAC8 BMC session 上限问题

## ⚠️ Known Limitations

- **iDRAC9+ `redfish_oem` 控制路径**未在真机验证(本项目目标机仅 iDRAC8 R730);代码骨架就绪,字段标 `# TODO: 待 iDRAC9+ 真机验证`
- **iDRAC8 Probe 取 host OS**:Redfish 通常不暴露;Dell OEM `DellSystem.HostOSName` 需 host 装 Dell iSM 服务后才有;否则 fallback `HostName`(iDRAC 配置的主机名,不严格是 OS)
- **macOS 不签名**:LaunchAgent 启动会被 Gatekeeper 拦,install.sh 自动 `xattr -d com.apple.quarantine`
- **PyInstaller / 三平台真装**:打包脚本 + 自启 unit 就绪,但实际 `pyinstaller build.spec` 由部署者本地跑(不进 CI/CD)

## 🚀 Next

```bash
git push                   # 推 main 到远程
git push origin v0.1.0     # 推 tag
```

如要发布到 GitHub Releases,把本文件内容贴到 release description。

## 🙏 Acknowledgments

- 设计参考:[tigerblue77/Dell_iDRAC_fan_controller_Docker](https://github.com/tigerblue77/Dell_iDRAC_fan_controller_Docker) · [kuan909608/dell-idrac-fan-controller-gpu](https://github.com/kuan909608/dell-idrac-fan-controller-gpu)
- Dell 官方:[iDRAC-Redfish-Scripting](https://github.com/dell/iDRAC-Redfish-Scripting) · [OMSDK](https://github.com/Dell/omsdk)
- 协议库:[pyghmi](https://opendev.org/x/pyghmi) · [httpx](https://www.python-httpx.org) · [Starlette](https://www.starlette.io) · [Vue 3](https://vuejs.org) · [vue-i18n](https://vue-i18n.intlify.dev) · [pywebview](https://pywebview.flowrl.com)
