# 从源码在 Linux 运行

Linux 适配使用现有白龙界面与动画，从源码运行。Windows 安装包、安装器和应用内程序更新不能用于 Linux，相关下载安装入口在 Linux 下禁用；源码和 Python 依赖需单独维护。此步骤不会迁移或修改已有安装的数据。

## 运行环境

- Python 3.12、uv 和可用的图形桌面环境。Wayland 会话还需要 XWayland；程序通过 xcb 运行，以支持人物拖动、位置保存及独立卡片跟随。
- 在同一台电脑安装并登录 Codex CLI。额度与会话读取使用当前用户的本机登录，不需要复制其他设备的登录令牌。
- 闲聊为可选功能；安全保存聊天密钥需要桌面 Secret Service、可用且已解锁的密钥环，以及 `secret-tool`。
- 打开 Codex 桌面端可使用 `codex-gui`，会话链接通过 `xdg-open` 交给系统处理，需要对应的桌面端和协议关联。桌面通知使用可选的 `notify-send`，声音使用可选的 `pw-play` 或 `paplay`；缺少通知或声音工具时跳过对应动作。

## 准备 Python 环境

先取得包含 Linux 补丁的源码。以下命令均在该源码的仓库根目录执行：

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements-linux.txt
```

## 下载与校验动画

Git 不保存大型动画。默认 512px 素材可从现有的 [light 素材 Release](https://github.com/shiki-sl/bailong-linux/releases/tag/materials-light-8849481e60e0b3f2314ec6a0) 下载，附件为：

- `bailong-light-8849481e60e0b3f2314ec6a0.zip`，约 590 MiB；
- `SHA256SUMS.txt`，用于完整 ZIP 校验；
- `material-manifest.json`，列出逐文件大小与 SHA-256，便于核对来源。

素材 ID 为 `8849481e60e0b3f2314ec6a0`，与源码 `app/material_catalog.json` 的 light 档匹配。该素材目录与此前 0.8.3 Linux 适配使用的目录相同；720px 高清素材不能替代此处的默认轻量目录。

下面的命令在校验成功后才解压。ZIP 内除 32 个素材文件外还带有根目录 `NOTICE.md` 及两份 `docs/upstream/` 来源说明，因此先解压到临时目录，只复制 `outputs/白龙桌宠素材/`，保留当前源码中的上游声明。

```sh
(
    set -eu
    BAILONG_MATERIALS_URL='https://github.com/shiki-sl/bailong-linux/releases/download/materials-light-8849481e60e0b3f2314ec6a0'
    BAILONG_MATERIALS_ZIP='bailong-light-8849481e60e0b3f2314ec6a0.zip'
    curl -fL --retry 3 -o "$BAILONG_MATERIALS_ZIP" "$BAILONG_MATERIALS_URL/$BAILONG_MATERIALS_ZIP"
    curl -fL --retry 3 -o SHA256SUMS.txt "$BAILONG_MATERIALS_URL/SHA256SUMS.txt"
    sha256sum -c SHA256SUMS.txt
    BAILONG_MATERIALS_TMP=$(mktemp -d)
    trap 'rm -rf "$BAILONG_MATERIALS_TMP"' EXIT HUP INT TERM
    .venv/bin/python -m zipfile -e "$BAILONG_MATERIALS_ZIP" "$BAILONG_MATERIALS_TMP"
    mkdir -p outputs
    cp -R "$BAILONG_MATERIALS_TMP/outputs/白龙桌宠素材" outputs/
)
```

必须看到 ZIP 校验结果为 `OK`；下载或校验失败时停止，不解压、不启动。也可从 Release 页面手动下载 ZIP 和校验文件，再执行校验与上述临时解压步骤。解压后的 `outputs/白龙桌宠素材/` 下应直接包含 `素材清单.json` 和动画目录，不需要运行任何 Windows EXE。

角色和动画的来源与使用范围见 [NOTICE.md](../NOTICE.md) 和 [原素材说明](upstream/ASSETS.md)。该 Release 仅提供资源；公开下载不额外授予商用、改编或再分发许可。

## 启动与可选集成

完成环境和素材准备后执行：

```sh
./start-linux.sh
```

脚本优先使用仓库内 `.venv/bin/python`；若没有此环境，可用 `BAILONG_PYTHON` 指定已安装依赖的 Python 可执行文件。设置、聊天和统计写入 `${XDG_DATA_HOME:-$HOME/.local/share}/BailongEnhanced/`，与 Codex 自身的数据分开。源码运行不会自动创建系统应用菜单入口。

登录自启、随 Codex 桌面端启动及聊天服务均可按需在设置中启用。自启项写入 `${XDG_CONFIG_HOME:-$HOME/.config}/autostart/`；保留源码目录和 Python 环境的位置后再启用。

Windows 的视频全屏自动让位尚未移植，Linux 下停用此检测，可手动切换置顶。当前文档不代表已完成这次适配在真实显示器、拖动、托盘或播放器上的验收；实际行为还取决于桌面环境。

## 源码检查

Linux CI 安装 `requirements-linux.txt`，编译检查 `app` 与 `tools`，再运行不依赖外部动画的 Linux 适配与生命周期帧测试：

```sh
PYTHONPATH=app QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest test_linux_support test_live_compaction.FrameTests
```

既有 Windows CI 保留。上述源码检查不部署或发布软件，也不能替代真实桌面验收。
