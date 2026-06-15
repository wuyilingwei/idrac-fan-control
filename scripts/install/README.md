# 自启动安装

按平台选目录。所有脚本假设 PyInstaller 产物 `idrac-fan-control(.exe)` 与 `config.json` 在同一目录。

## 流程

```
1. cd frontend && npm install && npm run build   # 产物 → ../app/static/
2. pip install pyinstaller pywebview
3. pyinstaller build.spec                         # 产物 → dist/idrac-fan-control(.exe)
4. mkdir -p /opt/idrac-fan-control && cp dist/idrac-fan-control /opt/idrac-fan-control/
5. cp config.example.json /opt/idrac-fan-control/config.json   # 然后 chmod 600
6. 跑对应平台 install 脚本
```

## Linux (systemd --user)

```bash
bash scripts/install/linux/install.sh /opt/idrac-fan-control
# 无头机器跨注销保活:
sudo loginctl enable-linger "$USER"
```

## macOS (LaunchAgent)

```bash
bash scripts/install/macos/install.sh /opt/idrac-fan-control
# 若 Gatekeeper 拦 (PLAN §12):
xattr -d com.apple.quarantine /opt/idrac-fan-control/idrac-fan-control
```

## Windows (计划任务)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install\windows\install-task.ps1 -InstallDir "C:\idrac-fan-control"
```

## 桌面 vs 无头

- **核心服务** (`python -m app` 或 `idrac-fan-control --no-window`):只跑 Starlette + ControlLoop;无头机器 / 自启动用。
- **桌面入口** (`python -m app.desktop` 或 `idrac-fan-control`):自动起服务 + 打开 pywebview 窗口;桌面端用。

## 卸载

| 平台 | 命令 |
|---|---|
| Linux | `systemctl --user disable --now idrac-fan-control && rm ~/.config/systemd/user/idrac-fan-control.service` |
| macOS | `launchctl unload ~/Library/LaunchAgents/io.github.idrac-fan-control.plist && rm ~/Library/LaunchAgents/io.github.idrac-fan-control.plist` |
| Windows | `Unregister-ScheduledTask -TaskName "idrac-fan-control" -Confirm:$false` |
