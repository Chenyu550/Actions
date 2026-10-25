# Node 24 Windows 7 兼容版

每天 **09:00（UTC+8）**，通过 Actions 检查官方 Node 索引中的最新 **Node24 正式版本**，与本仓库已有 Release/tag 的最高版本比较。

- 有更新则检出该版本的官方源码，应用兼容补丁，编译并发布文件。
- 没有更新：检查后直接结束，跳过 Windows 构建任务和编译。

## 下载

从本仓库的 [GitHub Releases](https://github.com/Chenyu550/Actions/releases) 下载：

| 文件 | 内容 |
| --- | --- |
| `node-v24.x.x-win7-x64.msi` | x64 安装包，包含 npm、npx、Corepack |
| `node-v24.x.x-win7-x64.zip` | 便携包，包含 Node、npm、npx、Corepack 和许可证 |
| `SHASUMS256.txt` | MSI 和 ZIP 的 SHA-256 校验值 |

Actions 中的 artifact 还包含 `build-info.json`、`applied.patch`、Win7 手动检查脚本与说明。`node24-win7-reports` artifact 保存导入表、包内运行输出和 MSI 解包日志。

## Win7 上使用

仓库的目标版本是 **Windows 7 SP1 64位**，原生运行，不需要 VxKex 或类似物。MSI 安装包的功能与官方版的一致。根据自己需要选择安装包或便携包。

## 补丁

前三份补丁来自 [Electron-for-windows-7](https://github.com/e3kskoy7wqk/Electron-for-windows-7/tree/1086a0a7c6b7105f300a4af8724e6d996ce3c347/v44.2.0/third_party/electron_node)（感谢大佬）。

| 补丁 | 作用 |
| --- | --- |
| `0001-libuv-hostname.patch` | 缺少 `GetHostNameW` 时使用回退实现 |
| `0002-libuv-realtime-clock.patch` | 缺少精确时钟 API 时使用 `GetSystemTimeAsFileTime` |
| `0003-libuv-process-title.patch` | 防止进程标题为空时继续读取 |
| `0004-node-and-msi-platform-check.patch` | Node 启动和 MSI 安装条件改为 Win7 SP1+ |
| `0005-v8-waitable-timer-fallback.patch` | 高精度计时器标志不支持时重试普通计时器 |

每次任务根据官方正式 tag，在工作区中更新本次构建的 Node 版本和源码 SHA。

使用的是官方 Windows 构建入口：

```bat
vcbuild.bat x64 vs2022 clang-cl no-cctest msi
```


