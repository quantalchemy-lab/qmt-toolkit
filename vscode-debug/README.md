# 大QMT VS Code 断点调试启动器

让大QMT里运行的 Python 策略可以用 VS Code 下断点、单步执行、查看变量。

配套文章：《大QMT调试终极指南：VSCode断点调试实战，附启动器》（公众号「量化炼金术」）

## 目录结构

| 文件 | 说明 |
| --- | --- |
| `启动器/启动器.rzrk` | 加密启动器，导入大QMT后作为"壳策略"运行 |
| `策略Demo/qmt_strategy_impl.py` | 最小策略示例，被调试的就是它 |
| `vscode/launch.json` | VS Code 附加调试配置 |
| `scripts/安装debugpy.bat` | 给 QMT 内置 Python 安装 debugpy 1.5.1 |
| `scripts/检查QMT环境.py` | 粘贴到 QMT 运行，检查 Python 版本、位数、debugpy 是否可用 |

## 适用环境

| 项目 | 要求 |
| --- | --- |
| QMT 客户端 | 内置 Python 3.6（64 位）的大QMT，例如国金证券 QMT 交易端 |
| debugpy | **1.5.1**（支持 Python 3.6 的最后一个版本） |
| VS Code | 安装扩展 Python、Python Debugger |
| 本机 Python | 任意带 pip 的 Python 均可，推荐 Miniconda 建一个 3.6 64 位环境 |

> 不同券商、不同版本客户端的内置 Python 可能不同。先用 `scripts/检查QMT环境.py` 确认版本和位数再安装。
> 内置 Python 3.12 的客户端不适用本 debugpy 版本，需改装 3.12 对应版本，且启动器未在该环境验证。

## 部署步骤

下文所有路径都是示例，请换成你自己的路径。

### 1. 安装 debugpy 到 QMT

```bat
conda create -n py36 python=3.6 -y
conda activate py36
scripts\安装debugpy.bat "D:\ProgramFiles\你的QMT安装目录"
```

脚本会把 debugpy 1.5.1 装到 `<QMT安装目录>\bin.x64\Lib\site-packages`。也可以手动执行：

```bat
python -m pip install debugpy==1.5.1 --upgrade --target "D:\ProgramFiles\你的QMT安装目录\bin.x64\Lib\site-packages" --python-version 3.6 --platform win_amd64 --implementation cp --abi cp36m --only-binary=:all: --no-deps -i https://pypi.tuna.tsinghua.edu.cn/simple
```

安装后重启 QMT，再运行 `scripts/检查QMT环境.py`，日志里应出现 `[DEBUGPY] OK 1.5.1 ...`。

### 2. 放置策略文件

把 `策略Demo/qmt_strategy_impl.py` 复制到你的策略目录，例如 `D:\quant\qmt_debug\`。

### 3. 配置 VS Code

1. 安装扩展：Python（ms-python.python）、Python Debugger（ms-python.debugpy）。
2. 用 VS Code 打开策略目录，把 `vscode/launch.json` 复制为 `<策略目录>\.vscode\launch.json`。

### 4. 导入启动器并配置参数

1. 在 QMT 策略编辑器中导入 `启动器/启动器.rzrk`。
2. 在该策略的参数设置里添加 5 个参数（**5 个都必须配置**，否则 `init` 会报 `NameError`）：

| 参数名 | 示例值 | 说明 |
| --- | --- | --- |
| `debug_mode` | `1` | 1 = 开启调试，0 = 关闭 |
| `debug_port` | `5678` | 调试端口，与 `launch.json` 的 `port` 一致 |
| `debug_wait_time` | `60` | 等待 VS Code 连接的秒数，0 = 不等待 |
| `strategy_path` | `D:\quant\qmt_debug` | 策略文件所在目录 |
| `strategy_module` | `qmt_strategy_impl` | 策略模块名，不带 `.py` |

### 5. 开始调试

1. 在 VS Code 的 `qmt_strategy_impl.py` 里打断点（例如 `on_bar` 第一行）。
2. 在 QMT 运行启动器，日志出现 `[DEBUG] Waiting for VS Code, timeout 60s`。
3. 在等待时间内，VS Code 按 F5 选择 `Attach QMT`。
4. 日志出现 `[DEBUG] Attached`，随后断点命中。

## 策略模块的写法

| QMT 回调 | 策略模块里对应的函数 | 是否必须 |
| --- | --- | --- |
| `init` | `on_init(ContextInfo, qmt)` | 必须 |
| `handlebar` | `on_bar(ContextInfo, qmt)` | 必须 |
| `after_init` | `on_after_init(ContextInfo, qmt)` | 可选 |
| `on_backtest_finished` | `on_backtest_finished(ContextInfo, qmt)` | 可选 |
| `stop` | `on_stop(ContextInfo, qmt)` | 可选 |

- QMT 注入的全局函数（`passorder`、`get_etf_info`、`timetag_to_datetime` 等）在策略模块里可以直接调用；`qmt` 参数是这些全局对象组成的字典。
- 每次在 QMT 重新运行启动器，策略模块会被重新加载，改完代码不用重启 QMT。只重载 `strategy_module` 本身，它引用的子模块不会自动重载。

## 常见问题

| 现象 | 原因与处理 |
| --- | --- |
| `NameError: name 'debug_port' is not defined` | 5 个参数没有配全 |
| `[DEBUG] Failed: ModuleNotFoundError('No module named debugpy')` | debugpy 没装到 QMT 的 `bin.x64\Lib\site-packages`，或装完没重启 QMT |
| pip 报 `Requires-Python >=3.10` / 找不到 1.8.x | Python 3.6 只能用 debugpy 1.5.1 |
| pip 报 `check_hostname requires server_hostname` | 旧版 pip 与系统代理不兼容，换一个新版 Python 的 pip 执行同一条命令（带 `--python-version 3.6` 等参数） |
| VS Code 提示连接被拒绝 / 超时 | 启动器没在等待，或已超过 `debug_wait_time`；端口不一致；重新运行启动器后在等待时间内附加 |
| 改了 `debug_port` 不生效 | 一个 QMT 进程只能启动一次调试监听，改端口要重启 QMT |
| `debug_mode=0` 断点仍然命中 | 上一次的调试连接还在，在 VS Code 按 Shift+F5 断开，或重启 QMT |
| 断点在每根历史 K 线都停 | 回放历史 bar 时每根都会调用 `on_bar`，给断点加条件，如 `ContextInfo.is_last_bar()` |
| 调试控制台看不到 `print` | 确认 `launch.json` 里有 `"redirectOutput": true`；QMT 日志窗口始终能看到 |
| 单步走出 `on_bar` 后编辑器"没反应" | 已进入启动器内部（显示为 `<string>`，无源码），按 F5 继续即可 |
| 策略里读写文件报 `Forbidden fileIO` | 部分 QMT 客户端限制策略代码读写文件，与调试无关 |

## 免责声明

仅用于在获准环境中调试策略代码，正式交易前请在模拟盘充分验证，并遵守券商软件协议与风控要求。
