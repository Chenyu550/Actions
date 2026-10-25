# Node.js v24.20.0：Windows 7 SP1 x64 实验构建

把本包**全部内容**放进你自己的 GitHub 仓库根目录，保留隐藏的 `.github` 目录，然后进入 **Actions → Build Node 24 for Windows 7 (experimental) → Run workflow**。

工作流会检出官方 Node 源码，应用补丁，使用 VS 2022 自带的 ClangCL 编译，并生成 **MSI 安装包和 ZIP 便携包**。运行时独立于 Electron/VxKex；实际 Win7 兼容性须以真机测试为准。本次交付的是构建工程，交付时的验证范围见 `VALIDATION.md`。

## 下载编译结果

运行成功后，在该次 Actions 页的 **Artifacts** 下载 `node-v24.20.0-win7-x64-experimental`。解开 artifact 后得到：

| 文件 | 用途 |
| --- | --- |
| `node-v24.20.0-win7-x64.msi` | 未签名的 x64 安装包，包含 npm、npx、Corepack 和安装界面 |
| `node-v24.20.0-win7-x64.zip` | 便携包，包含 `node.exe`、npm、npx、Corepack 和许可证 |
| `SHASUMS256.txt` | 顶层文件的 SHA-256 校验值 |
| `build-info.json`、`applied.patch` | 固定源码/补丁版本、校验值和实际应用的源码改动 |
| `smoke.cjs`、`fixtures/` | 可在 Win7 上再次运行的功能测试 |
| `COMPATIBILITY.txt` | 当前验证范围 |

另一个 artifact `node24-win7-reports` 保存导入表、测试输出、MSI 解包日志；检查失败时也会上传已有报告。没有自动创建 GitHub Release。

ZIP 内的目录沿用上游名称 `node-v24.20.0-win-x64`。程序报告的版本仍是 `v24.20.0`，未修改 Node 模块 ABI，也未替换 V8、OpenSSL 等依赖的版本。

## 实际应用的补丁

前三份文件来自 [Electron-for-windows-7 的 v44.2.0 补丁目录](https://github.com/e3kskoy7wqk/Electron-for-windows-7/tree/1086a0a7c6b7105f300a4af8724e6d996ce3c347/v44.2.0/third_party/electron_node)，保留原始字节，并在 `patches/manifest.json` 记录来源和 SHA-256。

| 补丁 | 作用 |
| --- | --- |
| `0001-libuv-hostname.patch` | 为 Win7 缺少的 `GetHostNameW` 提供回退 |
| `0002-libuv-realtime-clock.patch` | 动态查找精确时钟 API，缺少时使用 `GetSystemTimeAsFileTime` |
| `0003-libuv-process-title.patch` | 防止进程标题为空时继续读取 |
| `0004-node-and-msi-platform-check.patch` | 将 Node 启动检查和 MSI 安装条件改为 Win7 SP1 起，标明社区构建 |
| `0005-v8-waitable-timer-fallback.patch` | 高精度计时器标志不受支持时，重试普通计时器 |

Node 来源：[nodejs/node v24.20.0](https://github.com/nodejs/node/tree/v24.20.0)，固定提交 `71b8b174857e25106d39b61a9e6f30d927da8b01`。

补丁仓库固定提交：`1086a0a7c6b7105f300a4af8724e6d996ce3c347`。

工作流先验证源码提交、版本号和所有补丁摘要，再逐份执行 `git apply --check` / `git apply`。不使用模糊合并或忽略失败。更新 Node 版本时，需要重新移植和验证补丁，不能只改工作流里的版本字符串。

## 编译与检查

编译使用 [Node 官方 vcbuild](https://github.com/nodejs/node/blob/v24.20.0/vcbuild.bat)：

```bat
vcbuild.bat x64 vs2022 clang-cl no-cctest msi
```

`vcbuild` 默认就是 Release 配置。这里没有显式传 `release`，因为该参数还会开启 LTCG 和额外的 C++ 测试目标。没有传 `build-release` 或 `sign`，因此不需要官方签名证书。`msi` 参数同时生成完整的分发目录，随后用 7-Zip 将该目录压缩为 ZIP，省去额外的符号包。WiX 4 由上游 MSI 项目通过 NuGet 还原，不需要手工装 WiX 3。`DOTNET_ROLL_FORWARD=Major` 允许 WiX 构建工具使用 runner 的较新 .NET 运行库。

构建在 `windows-2022` 上执行，检查包括：

- 验证 ZIP 结构、解压 ZIP，使用其中的 `node.exe` 执行测试。
- 检查 PE 头的最低系统版本和一组已知 Win7 缺失 API 的普通/延迟导入，保留完整导入表。
- 执行主机名、标题、计时、Unicode 文件、子进程、Worker、Atomics、DNS、加密、回环 TLS/HTTPS、Intl、SQLite 测试。
- 使用包内的 `node.exe` 执行包内 npm、npx、Corepack CLI；不依赖 runner 自带的 Node。
- 使用 `msiexec /a` 管理解包 MSI，比较 MSI 和 ZIP 的 `node.exe` 哈希，并重新测试 MSI 内的程序。

**以上通过也不等于 Win7 兼容性已确认。** 导入表检查只覆盖已知问题，无法证明动态 API 调用和所有第三方原生扩展都兼容；`msiexec /a` 也不是实际安装测试。

MSI 保留了上游 Node 的安装目录、注册表路径和升级标识，以沿用单一 Node 安装行为。真机试装前请先处理已有 Node 安装；本包不会创建一个与官方 Node 隔离的第二套全局安装。

## 在 Windows 7 上完成最终验证

目标是 **Windows 7 SP1 x64**，不提供 x86 或 ARM64。系统应具备适用的 UCRT/运行库及 DLL 安全加载更新（如 KB2999226、KB2533623 或其替代更新）；是否需要补装取决于现有系统和实际报错。不要覆盖系统 DLL。

先在 Win7 上解开构建 artifact，再将其中的 Node ZIP 也解压到同一目录。假设该目录是 `C:\node24-test`，用 CMD 执行：

```bat
cd /d C:\node24-test
node-v24.20.0-win-x64\node.exe -v
node-v24.20.0-win-x64\node.exe smoke.cjs
node-v24.20.0-win-x64\npm.cmd -v
```

再测试实际项目，并在可回滚的 Win7 环境中验证 MSI 安装、PATH、启动和卸载：

```bat
msiexec /i node-v24.20.0-win7-x64.msi /L*v node24-win7-install.log
```

`fixtures/localhost-key.pem` 是测试专用的公开私钥，仅用于回环 HTTPS 测试。

## 本次交付前的验证

具体检查结果见 `VALIDATION.md`。本地环境无法完成 Windows 编译或 Win7 运行测试；这些状态也明确写入工作流的结果摘要和 `build-info.json`。
