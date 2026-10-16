FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu \
    TOKENIZERS_PARALLELISM=false

# marker-pdf declares torch as a dependency; install the CPU wheel first so the
# conversion client stays lightweight. GPU inference is handled by the separate
# vLLM service over the Compose network. streamlit/streamlit-ace power marker_gui.
RUN pip install --upgrade pip \
    && pip install "torch>=2.7,<3" \
    && pip install "marker-pdf[full]==2.0.0" "streamlit>=1.37.1" "streamlit-ace>=0.1.1"

# Optional deployment patch: let the Streamlit GUI read the LLM service and
# config JSON from environment variables (MARKER_LLM_SERVICE / MARKER_LLM_CONFIG)
# so a non-Gemini, OpenAI-compatible provider such as DeepSeek can be used.
COPY repo/marker/scripts/streamlit_app.py /usr/local/lib/python3.12/site-packages/marker/scripts/streamlit_app.py

WORKDIR /workspace
CMD ["--help"]
