# marker-zh-gui

基于 [Marker 2.0](https://github.com/datalab-to/marker) 官方 Streamlit 图形界面的中文增强版补丁与部署配置。

本项目只替换 Marker 自带的 `marker_gui` 前端脚本，不修改 OCR / 版面分析 / 表格识别等核心管线，因此转换质量与官方 `marker-pdf==2.0.0` 完全一致。

## 相比官方界面多了什么

| 能力 | 官方界面 | 本补丁 |
|---|---|---|
| 界面语言 | 英文 | 中文 |
| 文件上传 | 单个 | 多选，批量转换 |
| 进度显示 | 无 | 逐文件进度与状态 |
| 结果下载 | 无 | 每个文件独立下载按钮 |
| 打包下载 | 无 | 一键下载 `marker_results.zip` |
| 多结果切换 | 无 | 下拉框切换预览 |
| LLM 服务 | 固定 Gemini | 支持通过环境变量改用 OpenAI 兼容服务（如 DeepSeek） |
| 结果保留 | 刷新即丢失 | 保存在浏览器会话，可手动清空 |

支持格式：PDF、PNG、JPG、JPEG、GIF、WEBP、PPTX、DOCX、XLSX、HTML、EPUB。图片会自动转换为 PDF 再送入转换管线。

## 目录结构

```
.
├─ patch/
│  └─ streamlit_app.py          替换官方英文界面的中文增强版
├─ deploy/
│  ├─ Dockerfile                Marker 客户端镜像定义（含界面依赖与补丁）
│  ├─ docker-compose.yml        GPU 推理服务 + 命令行 + 图形界面编排
│  ├─ llm-config.json           OpenAI 兼容 LLM 配置模板（需填自己的 Key）
│  ├─ convert.ps1               PowerShell 单文件转换脚本
│  └─ convert.cmd               CMD 单文件转换脚本
├─ docs/
│  └─ 完整使用说明.md            部署、日常操作、显存调优、常见问题
├─ 操作手册.md                    重启电脑后从零开始跑起来的步骤清单
└─ LICENSE
```

## 快速开始

前置条件：

- Windows 10/11 + Docker Desktop（WSL2 后端）
- NVIDIA 显卡驱动 + 可用的 `nvidia` 容器运行时
- 首次运行需要下载 `vllm/vllm-openai` 镜像与 `datalab-to/surya-ocr-2` 模型，耗时较长

```powershell
cd <项目目录>\deploy

# 1. 启动 GPU 推理服务
docker compose up -d vllm

# 2. 构建带中文界面的客户端镜像
docker compose --profile cli build marker

# 3. 启动中文图形界面
docker compose --profile gui up -d gui
```

浏览器打开：

```
http://127.0.0.1:18102
```

详细步骤见 [操作手册.md](操作手册.md) 与 [docs/完整使用说明.md](docs/完整使用说明.md)。

## 如何替换官方英文界面

官方 `marker_pdf` 包中，界面脚本位于：

```
<Python site-packages>/marker/scripts/streamlit_app.py
```

以官方 Python 3.12 slim 镜像为例：

```
/usr/local/lib/python3.12/site-packages/marker/scripts/streamlit_app.py
```

替换方式任选一种：

### 方式一：Docker 构建时复制（本项目采用）

在 `Dockerfile` 中安装完 `marker-pdf` 之后，直接覆盖该文件：

```dockerfile
RUN pip install --upgrade pip \
    && pip install "torch>=2.7,<3" \
    && pip install "marker-pdf[full]==2.0.0" "streamlit>=1.37.1" "streamlit-ace>=0.1.1"

COPY repo/marker/scripts/streamlit_app.py /usr/local/lib/python3.12/site-packages/marker/scripts/streamlit_app.py
```

注意：

- `COPY` 的源文件必须位于 Docker 构建上下文内，路径按你自己的项目结构调整
- 目标路径必须与镜像内 Python 版本一致（3.12 对应 `python3.12`）

### 方式二：本地源码模式

直接修改克隆下来的 Marker 源码：

```powershell
git clone https://github.com/datalab-to/marker.git
# 用本仓库 patch/streamlit_app.py 覆盖下面的文件
# marker/scripts/streamlit_app.py
pip install -e .
marker_gui
```

### 方式三：已构建镜像内替换

```powershell
docker cp patch/streamlit_app.py <容器名>:/usr/local/lib/python3.12/site-packages/marker/scripts/streamlit_app.py
docker restart <容器名>
```

该方式在容器重建后会失效，长期使用建议用方式一。

### 补丁做了什么

1. **中文界面**：将标题、上传框、选项、按钮、提示文案改为中文。
2. **批量转换**：`st.file_uploader(..., accept_multiple_files=True)`，逐个转换并显示进度。
3. **结果下载**：
   - 单文件：`st.download_button` 导出 `.md` / `.json` / `.html`
   - 多文件：打包为 `marker_results.zip`，图片一并写入
4. **结果持久化**：转换结果写入 `st.session_state.marker_results`，避免界面重跑后结果消失。
5. **LLM 服务可配置**：读取环境变量 `MARKER_LLM_SERVICE` 与 `MARKER_LLM_CONFIG`，从而把默认的 Gemini 换成任意 OpenAI 兼容服务。

## 配置 LLM（可选）

界面左侧的“使用 LLM”默认走 Gemini，需要改为 DeepSeek 等 OpenAI 兼容服务时，编辑 `deploy/llm-config.json`：

```json
{
  "llm_service": "marker.services.openai.OpenAIService",
  "openai_base_url": "https://api.deepseek.com",
  "openai_model": "deepseek-flash",
  "openai_api_key": "sk-REPLACE_WITH_YOUR_API_KEY",
  "openai_image_format": "png",
  "timeout": 120,
  "max_retries": 2
}
```

`docker-compose.yml` 中通过以下环境变量指向该配置：

```yaml
MARKER_LLM_SERVICE: marker.services.openai.OpenAIService
MARKER_LLM_CONFIG: /config/llm-config.json
```

不使用 LLM 时无需填写 Key，也不会产生 API 费用。

## 隐私说明

本仓库不包含任何 API Key、账号、邮箱或本机绝对路径。`deploy/llm-config.json` 中的密钥为占位符，使用前请替换为你自己的 Key，并且不要把填好的文件提交到公开仓库。

## 许可

上游 Marker 采用 Apache-2.0 许可，本仓库为基于其前端脚本的修改版，同样以 Apache-2.0 发布，详见 [LICENSE](LICENSE)。
