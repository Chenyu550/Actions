# Node 24：Windows 7 x64 每日更新与自动发布

每天 **09:00（Asia/Singapore，UTC+8）**，GitHub Actions 检查官方 Node 分发索引中的最新 **24.x.x 正式版本**，与本仓库已有正式 Release/tag 的最高版本比较。

- 有更新：检出该版本的官方源码，应用 Win7 补丁，编译并发布 MSI、ZIP 和 SHA-256 文件。
- 没有更新：检查后直接结束，Windows 构建任务显示 `skipped`，不重新编译。
- 排除 RC、nightly、其他主版本及草稿/预发布 Release；按数字比较版本，而不是按字符串或发布时间排序。
- 你已创建的 `24.20.0` Release 和 tag 会作为现有版本保留，不重复创建或覆盖。

## 触发与执行顺序

工作流名称：**Daily Node 24 Windows 7 releases**。除每日定时外，也可以在 **Actions → Run workflow** 手动检查；相关工作流、脚本、补丁更新时也会触发同样的检查。

执行顺序：

1. 在轻量 Linux 任务中比较官方版本与本仓库 Release/tag。
2. 仅在有更新时启动 Windows 2022 构建，锁定官方 tag 对应的确切源码提交。
3. 校验补丁摘要并应用补丁，编译 `node.exe`、MSI，打包 ZIP。
4. 先上传 Actions artifact，再把 MSI、ZIP、SHA-256 文件上传到 GitHub Release。
5. 最后执行原有包内校验；校验失败也不会撤回已上传的安装包。

同一仓库的发布流程串行执行，避免重复构建/发布同一个版本。新 tag 沿用 `24.20.0` 的命名方式，例如 `24.22.1`，指向生成该发布的工作流源码提交；官方 Node 源码提交另写入发布说明和构建记录。

发布先作为本工作流的草稿创建，三个文件上传完成后才正式发布。已发布的版本不覆盖；上传中断留下的本工作流草稿可在重试时恢复，不会修改无关草稿。

## 下载文件

优先从本仓库的 [GitHub Releases](https://github.com/Chenyu550/Actions/releases) 下载：

| 文件 | 内容 |
| --- | --- |
| `node-v24.x.x-win7-x64.msi` | 未签名的 x64 安装包，包含 npm、npx、Corepack |
| `node-v24.x.x-win7-x64.zip` | 便携包，包含 Node、npm、npx、Corepack 和许可证 |
| `SHASUMS256.txt` | MSI 和 ZIP 的 SHA-256 校验值 |

Actions 中的 `node-v24.x.x-win7-x64-experimental` artifact 还包含 `build-info.json`、`applied.patch`、Win7 手动检查脚本与说明。`node24-win7-reports` artifact 保存导入表、包内运行输出和 MSI 解包日志，失败时也上传已有报告。

安装包是在运行校验之前上传的，请同时查看对应工作流的后续结果。Windows 2022 上通过校验不等于已验证 Win7 真机兼容性。

## 补丁与源码锁定

前三份补丁来自 [Electron-for-windows-7 的 v44.2.0 补丁目录](https://github.com/e3kskoy7wqk/Electron-for-windows-7/tree/1086a0a7c6b7105f300a4af8724e6d996ce3c347/v44.2.0/third_party/electron_node)，保留原始字节；来源与 SHA-256 记录在 `patches/manifest.json`。

| 补丁 | 作用 |
| --- | --- |
| `0001-libuv-hostname.patch` | 缺少 `GetHostNameW` 时使用回退实现 |
| `0002-libuv-realtime-clock.patch` | 缺少精确时钟 API 时使用 `GetSystemTimeAsFileTime` |
| `0003-libuv-process-title.patch` | 防止进程标题为空时继续读取 |
| `0004-node-and-msi-platform-check.patch` | Node 启动和 MSI 安装条件改为 Win7 SP1 起，标明社区构建 |
| `0005-v8-waitable-timer-fallback.patch` | 高精度计时器标志不支持时重试普通计时器 |

仓库清单记录补丁基线；每次任务根据官方正式 tag，在工作区中更新本次构建的 Node 版本和源码 SHA，不提交回仓库。补丁摘要仍固定验证。若将来的 Node 24 更新无法干净应用补丁，任务会明确失败，不忽略补丁错误。

使用官方 Windows 构建入口：

```bat
vcbuild.bat x64 vs2022 clang-cl no-cctest msi
```

默认采用 Release 配置，不启用额外 C++ 测试目标或官方签名流程。MSI 参数生成完整分发目录，随后用 7-Zip 打包；没有新增测试流程。

GitHub 自动提供仓库范围的 `GITHUB_TOKEN`。版本检查任务只读；构建任务使用 `contents: write` 发布 Release，不需要额外保存个人访问令牌。

## Win7 上使用

目标是 **Windows 7 SP1 x64**，运行时独立于 Electron/VxKex。先解压 ZIP，在 Win7 上执行 `node.exe -v`、`npm.cmd -v`，再运行实际项目。系统需要适用的运行库和更新；不要覆盖系统 DLL。

MSI 沿用上游 Node 的安装目录和升级标识，安装前请处理已有 Node 安装。更完整的检查可以使用 artifact 附带的 `smoke.cjs` 和 `fixtures/`，其中私钥仅供本机回环 HTTPS 测试。

本次交付和升级的历史验证记录见 `VALIDATION.md`。
