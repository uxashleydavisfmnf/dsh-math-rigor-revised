<div align="center">

# ∷ math-rigor ∷

**可审计的数学证明工具链，作为 DSH 插件运行：本地 stdio MCP 服务器（23 个工具）+ 流程 skill + 两个 slash 命令**

*Auditable mathematical proving for DeepSeek Harness: a local stdio MCP server (23 tools), a bundled workflow skill, and two slash commands.*

> `∀ ε > 0, ∃ δ > 0, s.t. |x − a| < δ ⟹ |f(x) − L| < ε`

[![GitHub stars](https://img.shields.io/github/stars/bauerelizabeth07139/dsh-math-rigor.svg?color=gold)]() [![GitHub forks](https://img.shields.io/github/forks/bauerelizabeth07139/dsh-math-rigor.svg)]() [![GitHub issues](https://img.shields.io/github/issues/bauerelizabeth07139/dsh-math-rigor.svg)]()
[![GitHub release](https://img.shields.io/github/v/release/bauerelizabeth07139/dsh-math-rigor.svg?color=8A2BE2)]() [![CI status](https://img.shields.io/github/actions/workflow/status/bauerelizabeth07139/dsh-math-rigor/tests.yml.svg?branch=main)]()
[![version](https://img.shields.io/badge/plugin-0.2.5-8A2BE2.svg)]() [![License](https://img.shields.io/badge/license-MIT-brightgreen.svg)](LICENSE) [![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)]() [![MCP](https://img.shields.io/badge/MCP-2.x-8A2BE2.svg)]() [![tools](https://img.shields.io/badge/MCP%20tools-23-9cf.svg)]()

</div>

> **0.2.5**:改用**项目阶梯**验证——从"1000 项求和"到"Schur 不等式"到"带引理的完整证明"再到"服务器还活不活"，共 9 级。结果修掉 3 个缺陷:
> ① **证明引理反而让整份证明判为 `flawed`**——`proves_lemma` 把证明步骤的引用抄到引理上，引理在文件里更早，于是被当成"前向引用"（任何多引理的机器校验证明都会中招）；
> ② **指数归纳判不出来且很慢**——`2^n >= n+1` 的归纳步被原样交给 z3（`2^n` 与 `2^(n+1)` 是两个不相干的幂项），21.7s 后仍 `undecided`；现在先做 `a^(k+1) = a·a^k` 再判定，**0.02s `proven`**，`2^n > n^2`、`n < 2^n`、`3^n >= 1+2n` 也随之可证；
> ③ **`i` 没被当成虚数单位**——`(cos x + i sin x)^3` 展开出 `i**3*sin(x)**3`，棣莫弗公式与欧拉恒等式都证不了。现在裸 `i` 视为 `I`，但被 `Sum`/量词绑定、或用 `variables`/`substitutions` 声明时仍作符号。
> 稳定性一并验证：80 步会话换进程重载、1200 项表达式、400 层嵌套、12 条流水线并发、20 种畸形输入、750 次连续调用无泄漏。详见 [CHANGELOG.md](CHANGELOG.md)。
>
> **0.2.4**:用真实数学重新测了一遍——不是"工具不崩"，而是"答案对不对"。这一轮发现 7 个缺陷,其中 5 个会返回**数学上错误的结论**:
> `x = 1 | x = 2` 曾被解析成三个合取式（于是 `n^2 % 4 = 0 | n^2 % 4 = 1` 这个真命题被判为 `refuted`，还附了个"反例" `n = 0`）；
> `symbolic_eval` 的 `sum`/`product` 把算子应用了两次（`Sum(k,(k,1,100))` 回答 **505000**、`Product(k,(k,1,5))` 回答 **120⁵**、Basel 求和回答 **`oo`**）；
> `verify_identity` 遇到二项式求和会**永不返回**；声明的整数域没在抽样时生效，真恒等式可能被"反驳"；
> `2^n` 会把 z3 拖进超越数理论并**无视求解器超时**（实测 2s 超时下 40s 仍在跑），而 `prime` 这类不可解释谓词曾让 z3 用"素数集为空"的模型把**欧几里得定理判成 `refuted`**。
> 另有审计漏洞（`2 + 2 = 5` 标成 `premise` 就能混成 `sound_with_gaps`）与 `diff arctan(x)` 返回未求值导数。同时把整除类命题的证明提速约 10 倍（`6 | n^3 - n` 30s → 3.1s）。详见 [CHANGELOG.md](CHANGELOG.md)。
>
> **0.2.3**:并发工具调用不再能杀死服务器——z3 的全局上下文不是线程安全的，而 MCP 传输可能同时派发多个请求；`rigor/engine.py` 现在用一把进程级 `RLock` 串行化引擎访问，SMT 入口与服务器工具守卫都会取它（0.2.3）。同类修正：`P(a) |- forall x: P(x)` 不再在 z3py 内部抛 `AttributeError`（谓词实参的排序现在跨出现统一）；无前提的 `arithmetic` 步（如 `2 + 2 = 5`）会被真正推翻，而不再只记为 unchecked；`symbolic_numeric` 对百万项求和不再挂死（精确闭式仅在约 2500 项以内尝试）。详见 [CHANGELOG.md](CHANGELOG.md)。
>
> **0.2.2**:`find_counterexample` 遵守量词里声明的定义域(0.2.1);`number_theory` 直接接受 JSON 整数(0.2.1);递归上限提高,长表达式不再在 ~300 项就报 RecursionError,超限时给出可操作的错误(0.2.2)。


---

## 这是什么

`dsh-math-rigor` 是一个 Cordis host plugin（DSH 0.2.x）。装进 profile 后它做三件事：

1. 准备并使用隔离的 Python 3.10+ 虚拟环境，以 **stdio** 启动 `server/math_rigor_server.py`，经 `@deepseek-ai/dsh-mcp-client` 接入 DSH；服务器注册的 23 个工具在 agent 侧显示为 `mcp__math_rigor__<tool>`（如 `mcp__math_rigor__proof_start`）。
2. 注册 bundled skill `math-rigor`（`source: 'bundled'`，模型与用户均可触发）。
3. 注册 slash 命令 `/prove` 与 `/audit-proof`。

设计上只坚持一件事：判定词汇不混用。

| 判定 | 含义 |
|---|---|
| `proven` | 否定式被证明不可满足，可以当结论用 |
| `refuted` | 给出了具体反例，命题为假 |
| `inconclusive` | 求解器未决定且未找到反例，**不是证明** |
| `verified` | 审计：每一步都被机器检查，目标已导出 |
| `sound_with_gaps` | 审计：结构成立、无被推翻项，但有未检查步骤（逐条列出） |
| `flawed` | 审计：有被推翻/无效步骤、未解除假设、未证明引理，或目标未导出 |

---

## 安装

**Desktop 应用** —— **Plugins → Add plugin**，填入 `https://github.com/bauerelizabeth07139/dsh-math-rigor`，装好后打开新 bundle 的开关。Desktop 启动的是保留 profile `desktop`。

**CLI** —— `--profile` 换成你实际启动的那个 profile；装进别的 profile，当前会话不会加载它。

```bash
dsh plugin --profile web add bauerelizabeth07139/dsh-math-rigor
```

**机器上没有 git** —— pnpm 解析 `owner/repo` 这类 git 简写时要调用 `git ls-remote`，改填 tarball 地址（把 `main` 换成 commit SHA 可固定构建；同一地址也能填进 Desktop 对话框）。

```bash
dsh plugin --profile web add https://codeload.github.com/bauerelizabeth07139/dsh-math-rigor/tar.gz/main
```

---

## 首次运行：先建好 Python 环境

**MCP 工具在 Python 环境存在之前不可用。** 两种建法：

**A. 让插件自己建** —— loader row 里打开 `setup`；插件在加载阶段创建 `<home>/venv` 并执行 `pip install -r requirements.txt`（需要网络，通常数分钟，会阻塞加载到 `setupTimeoutMs` 为止）。

```yaml
- id: dsh-math-rigor
  config:
    setup: true
```

**B. 先跑离线脚本** —— `--home` 必须与插件实际使用的 `home` 一致：

```text
Windows:  py -3 tools/setup_dsh.py --home "%USERPROFILE%\.dsh\math-rigor"
POSIX:    python3 tools/setup_dsh.py --home ~/.dsh/math-rigor
```

环境未就绪时，插件记一条 warning，注册 skill 与两个命令，**不挂载任何 MCP 工具**；两个命令以 error 返回，并给出需要执行的确切命令（含 `--home "<home>"`）和「重启 DSH profile」的提示。环境就绪后重启 profile。

| 依赖 | 版本 |
|---|---|
| Python | 3.10+ |
| `mcp` / `sympy` / `z3-solver` / `mpmath` | 2.2.0 / 1.14.0 / 5.1.0.0 / 1.3.0 |

这四项就是 `requirements.txt` 声明的全部依赖。加载时插件要求 `<home>/venv` 的解释器 ≥ 3.10、`import mcp, sympy, z3, mpmath` 成功，且 `venv/.requirements.sha256` 与 `requirements.txt` 的 sha256 一致；任一不满足即视为环境不合格。

---

## 配置

配置项来自 `index.js` 的 schemastery `Config`，写在 profile 的 loader row 里。

| 键 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `home` | string | `$DSH_HOME/math-rigor`；`DSH_HOME` 未设置时 `~/.dsh/math-rigor` | 数据目录；venv 在 `<home>/venv`，证明会话在 `<home>/sessions` |
| `python` | string | 空 | 显式指定解释器；空则探测 Windows 的 `python.exe`/`py`、其他平台的 `python3`/`python` |
| `setup` | boolean | `false` | 加载时创建 venv 并安装依赖 |
| `setupTimeoutMs` | number | `600000` | 1000–600000，步长 1；setup 总预算 |
| `toolCallTimeoutMs` | number | `300000` | 1000–600000，步长 1；单次 MCP 工具调用超时 |

在 loader row 里覆盖某一项：

```yaml
- id: dsh-math-rigor
  config:
    home: "D:/math-rigor-data"
    setupTimeoutMs: 900000
```

`home` 会以环境变量 `MATH_RIGOR_HOME` 传给 MCP 服务器；`~` 与 `~/...` 展开为当前用户主目录。

---

## 命令

| 命令 | 参数 | 行为 |
|---|---|---|
| `/prove` | `<mathematical proposition>` | 排入六阶段严格证明流程：形式化 → 策略 → 引理分解 → 逐步证明（每步机检）→ 机器审计 → 如实报告 |
| `/audit-proof` | `<proof text or math-rigor session id>` | 排入证明审查流程：拆成步骤 DAG、逐条读 verdict、结构性审查、给出问题清单 |

两者都**要求环境已就绪**，否则直接返回错误；参数为空时拒绝并提示用法。排入的消息以「Load the `math-rigor` skill before acting」开头，agent 先加载 skill 再按 `commands/*.md` 的正文执行。

---

## Skill

bundle 自带 `math-rigor` skill（`skills/math-rigor/SKILL.md`），在证明、推导、恒等式/不等式验证、归纳、整除、反例搜索、证明审查类任务上触发，规定六阶段流程与结果语义，并附 4 份参考文件：`inference-rules.md`（22 条逻辑规则 + 19 种非逻辑理由）、`strategies.md`、`notation.md`、`worked-examples.md`。

---

## 工具总表

`server/math_rigor_server.py` 共 23 个 `@server.tool` 注册。在 DSH 里调用请使用 `mcp__math_rigor__` 前缀后的完整名称。

| 分组 | 工具 | 用途 |
|---|---|---|
| 会话 | `proof_workflow` | 返回流程阶段、判定词汇表与审计强制检查项 |
| 会话 | `proof_start` | 开一个证明会话：登记问题、精确目标、每个符号的定义域 |
| 会话 | `proof_add_given` | 登记题面给定的前提（不证明，审计追踪其仍为假设） |
| 会话 | `proof_add_assumption` | 登记临时假设（之后必须由解消规则解除） |
| 会话 | `proof_add_lemma` | 登记引理义务，或声明 `assumed=true` 并披露 |
| 会话 | `proof_add_step` | 加一步并**立即机检**，返回 `verified`/`refuted`/`invalid`/`unchecked` |
| 会话 | `proof_validate` | 审计整个证明：引用图、假设解除、引理、目标是否导出、机器覆盖率 |
| 会话 | `proof_status` | 查看会话；空参则列出全部会话 |
| 会话 | `proof_export` | 导出 markdown / LaTeX / JSON，含每步理由与审计判定 |
| 逻辑 | `logic_check_step` | 单步推理：形状是否匹配规则 + 语义是否成立 |
| 逻辑 | `logic_entails` | 前提是否蕴含结论，返回 `proven` 或带反例赋值的 `refuted` |
| 逻辑 | `logic_truth_table` | 纯命题逻辑完全枚举（最多 10 个变量） |
| 逻辑 | `logic_rules` | 列出全部推理规则（可按 propositional / predicate / equality 过滤） |
| 验证器 | `verify_identity` | 两个表达式是否为同一个函数 |
| 验证器 | `verify_inequality` | 带定义域的全局不等式（如 `x + 1/x >= 2`，x > 0） |
| 验证器 | `verify_forall` | 任意全称命题：整除、奇偶、界、代数恒等式、量化逻辑 |
| 验证器 | `verify_induction` | 归纳法：基例 + `k >= start & P(k) -> P(k+1)` |
| 验证器 | `verify_limit` | 极限值（符号 + 数值；`oo` 表无穷，`+`/`-` 表单侧） |
| 验证器 | `find_counterexample` | 找反例：先问 SMT，再扫显式区间，最后采样 |
| 符号 | `symbolic_eval` | 单次符号运算：simplify/expand/factor/diff/integrate/limit/series/solve/sum/… |
| 符号 | `symbolic_numeric` | 高精度求值，并报告结果是否为精确整数/有理数及精确分数 |
| 符号 | `expr_normalise` | 规范化成 latex / text / sympy 形式，确认能解析 |
| 数论 | `number_theory` | 精确整数运算：is_prime、factorize、totient、gcd/lcm、bezout、crt、legendre、jacobi、fibonacci、… |

---

## 安全

证明器的输入是数学表达式，所以"绝不用 `eval` 求值输入"是它的安全底线；写文件、起进程、联网
同样有明确边界。这些不是声明，而是 `tests/test_security.py`（22 项检查）逐条读本包自己的
文件来强制的事实，任何一条被越过都会直接失败：

| 面 | 行为 |
|---|---|
| 进程 | 只起 Python:探测解释器的短进程 + stdio 上的证明服务器;**从不经过 shell**,因此没有任何值会被当作命令解析 |
| 服务器环境 | 只给**一个**变量 `MATH_RIGOR_HOME`。Harness 的环境里还有模型 API key,服务器看不到 |
| 写文件 | 全部落在插件自己的家目录 `$DSH_HOME/math-rigor`(venv、哈希标记、状态),不写 profile、不写工作目录 |
| 读文件 | `$DSH_HOME`(来自环境)与交给工具的那份数学输入 |
| 网络 | 只有一次:首次使用时 `<venv>/python -m pip install -r requirements.txt`。证明过程本身完全离线 |
| 密钥 | 无 |
| 动态代码 | 无 —— 输入由自带词法/语法分析器(`server/rigor/ast_nodes.py`)解析成 AST,再翻译成 SMT-LIB 交给 z3、或用 sympy 构造器建表达式;全程没有 `eval`/`exec`/`compile` 输入 |

`requirements.txt` 里每个包都钉死到精确版本(`mcp==2.2.0`、`sympy==1.14.0`、
`z3-solver==5.1.0.0`、`mpmath==1.3.0`),所以下载内容在下载之前就是可审计的;插件把该文件的
SHA-256 记在 venv 旁的标记里,哈希不变就不再装。完整说明见 [SECURITY.md](SECURITY.md)。

### 五级验证

社区标准是"先审计、后五级验证":组合 → 启动冒烟 → 健康检查 → 全量启动 → 功能实测。
前四级只说"能加载",第五级才说"真的证出来了"。本包在 `plugintest` profile 上的证据:

| 级别 | 检查 | 结果 |
|---|---|---|
| L1 组合 | bundle 在组合树里正确挂载 | `dsh --profile plugintest --dump-config` → exit 0,树中出现 `dsh-math-rigor` |
| L2 冒烟 | 入口模块按 loader 方式加载 | `index.js` 导入成功、配置 schema 解析通过 |
| L3 健康 | 对发布文件做静态审计 | `python tests/test_security.py` → 22/22;`plugin_audit.py` → 0 条 high |
| L4 全量启动 | 宿主半注册工具与 skill,并起 MCP 服务器 | `tests/test_mcp_stdio.py`(stdio 握手与 23 个工具) |
| L5 功能实测 | 真的证明/证伪一条命题 | `tests/run_all.py` 全模块通过(parse/translate/smt/logic/symbolic/verify/proof/mcp) |

---

## 故障排查

**(a) 装完后没有 `mcp__math_rigor__*` 工具。** 环境没建好。按「首次运行」建 `<home>/venv` 后重启 profile；`setup: true` 时看日志里的 warning，其中带着具体原因（找不到 Python、`pip` 失败、超时等）。

**(b) bundle 完全没加载。** 在 DSH 0.2.x 上，peer 版本范围不匹配会让 Cordis **整体跳过** bundle，而不是只丢工具。发布的 0.2.0 声明 `>=0.1.5-rc.1 <0.2.0-0 || >=0.2.0-rc.0 <0.3.0-0`（针对 `@deepseek-ai/dsh-commands`、`dsh-llm`、`dsh-mcp-client`、`dsh-skill`），先核对 DSH 版本是否落在范围内，别照着过期的范围说明排查。

**(c) `pip` 需要网络。** 建 venv 和装依赖都要联网；走代理时在 setup 之前设置 `PIP_INDEX_URL`，例如 `$env:PIP_INDEX_URL = "https://your-mirror.example/simple"`。

**(d) 重建环境。** 删掉 venv（`rm -rf "<home>/venv"`，或整个删掉 `<home>`）后重跑 `tools/setup_dsh.py --home "<home>"`。

---

## English

### What it is

`dsh-math-rigor` is a Cordis host plugin for DSH 0.2.x. It prepares an isolated Python 3.10+ virtual environment and launches `server/math_rigor_server.py` as a **stdio MCP server** through `@deepseek-ai/dsh-mcp-client`, so the server's 23 tools reach the agent as `mcp__math_rigor__<tool>`. It also registers one bundled skill (`math-rigor`) and two slash commands (`/prove`, `/audit-proof`).

Its contract: `proven` / `refuted` / `inconclusive` are never conflated, and a proof audit separates `verified` / `sound_with_gaps` / `flawed`, reporting unproven steps instead of hiding them.

### Install

- **Desktop app:** Plugins → Add plugin → `https://github.com/bauerelizabeth07139/dsh-math-rigor`, then switch the new bundle on. The Desktop app boots the reserved `desktop` profile.
- **CLI:** `dsh plugin --profile web add bauerelizabeth07139/dsh-math-rigor` — install into the profile you actually boot.
- **No git on the machine:** pnpm resolves a git shorthand with `git ls-remote`, so use the tarball URL instead: `dsh plugin --profile web add https://codeload.github.com/bauerelizabeth07139/dsh-math-rigor/tar.gz/main` (pin a commit SHA in place of `main` for a fixed build). The same address works in the Desktop dialog.

### First run

The MCP tools are unavailable until the Python environment exists. Either set `setup: true` in the loader row's `config:` and let the plugin build `<home>/venv` and run `pip install -r requirements.txt` (network access, several minutes), or run the offline helper first:

```text
Windows:  py -3 tools/setup_dsh.py --home "%USERPROFILE%\.dsh\math-rigor"
POSIX:    python3 tools/setup_dsh.py --home ~/.dsh/math-rigor
```

Until then the plugin logs a warning, registers the skill and the commands, and mounts no MCP tools; the commands answer with the exact command to run.

Requirements: Python 3.10+, `mcp==2.2.0`, `sympy==1.14.0`, `z3-solver==5.1.0.0`, `mpmath==1.3.0`.

### Configuration

| Key | Type | Default | Notes |
|---|---|---|---|
| `home` | string | `$DSH_HOME/math-rigor`, else `~/.dsh/math-rigor` | venv at `<home>/venv`, sessions at `<home>/sessions` |
| `python` | string | empty | explicit interpreter; empty probes `python.exe`/`py` on Windows, `python3`/`python` elsewhere |
| `setup` | boolean | `false` | build the venv on load |
| `setupTimeoutMs` | number | `600000` | 1000–600000 |
| `toolCallTimeoutMs` | number | `300000` | 1000–600000 |

```yaml
- id: dsh-math-rigor
  config:
    setup: true
```

### Commands

| Command | Input | Queues |
|---|---|---|
| `/prove` | `<mathematical proposition>` | the six-stage rigorous proof workflow, each step machine-checked as it is added |
| `/audit-proof` | `<proof text or math-rigor session id>` | the proof-audit workflow: step DAG, per-step verdicts, structural review, ranked flaw list |

Both require the environment to be ready; otherwise they return an error naming the setup command to run.

### Skill and tools

The bundled `math-rigor` skill carries the six-stage process and four reference files (`inference-rules.md`, `strategies.md`, `notation.md`, `worked-examples.md`). The 23 MCP tools, grouped: session/workflow `proof_workflow`, `proof_start`, `proof_add_given`, `proof_add_assumption`, `proof_add_lemma`, `proof_add_step`, `proof_validate`, `proof_status`, `proof_export`; logic `logic_check_step`, `logic_entails`, `logic_truth_table`, `logic_rules`; verifiers `verify_identity`, `verify_inequality`, `verify_forall`, `verify_induction`, `verify_limit`, `find_counterexample`; symbolic `symbolic_eval`, `symbolic_numeric`, `expr_normalise`; number theory `number_theory`. One-line purposes are in the table above.

---

## Legacy：ZCode 安装路径

math-rigor 最早是为 ZCode 写的，仓库里仍保留那条链路的脚本；它不是 DSH 的安装路径，DSH 用户可忽略本节。

| 入口 | 作用 |
|---|---|
| `install.ps1` / `install.sh` | Windows / macOS·Linux 安装：建 venv、装依赖、先自检服务器、再注册 MCP、复制 skill 与命令 |
| `tools/install.py` | 安装主体：把 `mcp.servers.math-rigor` 写进 `~/.zcode/cli/config.json`；把 `skills/math-rigor/` 复制进 `~/.zcode/skills/`；把 `commands/*.md` 复制进 `~/.zcode/commands/`。`ZCODE_HOME` 可覆盖 `~/.zcode` |
| `tools/install_check.py` | 按 ZCode 的加载规则校验 skill / 命令 / 配置 |
| `tools/verify_deployment.py` | 按 ZCode 的实际使用方式核对部署后的配置 |
| `tools/smoke_test.py` | 以 ZCode 的方式启动服务器并确认它能作答 |

ZCode 侧与 DSH 侧共用同一个服务器、同一套工具与判定词汇。

---

## License

[MIT](LICENSE) · by [bauerelizabeth07139](https://github.com/bauerelizabeth07139)
