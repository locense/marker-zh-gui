import io
import os
import re
import tempfile
import zipfile
from typing import Any, Dict

from marker.scripts.common import (
    load_models,
    parse_args,
    img_to_html,
    get_page_image,
    page_count,
)

os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
os.environ["IN_STREAMLIT"] = "true"

from marker.settings import settings
from streamlit.runtime.uploaded_file_manager import UploadedFile

import streamlit as st
from PIL import Image

from marker.converters.pdf import PdfConverter
from marker.config.parser import ConfigParser
from marker.output import text_from_rendered


def convert_file(fpath: str, config_parser: ConfigParser, model_dict: dict):
    config_dict = config_parser.generate_config_dict()
    config_dict["pdftext_workers"] = 1
    converter = PdfConverter(
        config=config_dict,
        artifact_dict=model_dict,
        processor_list=config_parser.get_processors(),
        renderer=config_parser.get_renderer(),
        llm_service=config_parser.get_llm_service(),
    )
    return converter(fpath)


def markdown_insert_images(markdown, images):
    image_tags = re.findall(
        r'(!\[(?P<image_title>[^\]]*)\]\((?P<image_path>[^\)"\s]+)\s*([^\)]*)\))',
        markdown,
    )
    for image in image_tags:
        image_markdown = image[0]
        image_alt = image[1]
        image_path = image[2]
        if image_path in images:
            markdown = markdown.replace(
                image_markdown, img_to_html(images[image_path], image_alt)
            )
    return markdown


def prepare_input(uploaded_file: UploadedFile, tmp_dir: str) -> str:
    """Save an uploaded file to disk, converting images to PDF when needed."""
    name = uploaded_file.name
    suffix = os.path.splitext(name)[1].lower()
    tmp_path = os.path.join(tmp_dir, name)
    with open(tmp_path, "wb") as f:
        f.write(uploaded_file.getvalue())

    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        pdf_path = os.path.join(tmp_dir, os.path.splitext(name)[0] + ".pdf")
        rgb = Image.open(tmp_path).convert("RGB")
        rgb.save(pdf_path, "PDF")
        return pdf_path
    return tmp_path


def zip_outputs(text: str, ext: str, images: dict, name: str) -> bytes:
    base = os.path.splitext(name)[0]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{base}/{base}.{ext}", text)
        for img_name, img in (images or {}).items():
            img_buf = io.BytesIO()
            img.save(img_buf, format=settings.OUTPUT_IMAGE_FORMAT)
            zf.writestr(f"{base}/{img_name}", img_buf.getvalue())
    return buf.getvalue()


def reset_failed(results: dict):
    failed = [k for k, v in results.items() if v.get("error")]
    for key in failed:
        del results[key]


st.set_page_config(page_title="Marker", layout="wide", page_icon="📄")

model_dict = load_models()
cli_options = parse_args()
_llm_service = os.environ.get("MARKER_LLM_SERVICE")
_llm_config = os.environ.get("MARKER_LLM_CONFIG")
if _llm_service:
    cli_options["llm_service"] = _llm_service
if _llm_config:
    cli_options["config_json"] = _llm_config

if "marker_results" not in st.session_state:
    st.session_state.marker_results = {}

st.markdown(
    """
# Marker 文档转换

支持 PDF、图片、DOCX、PPTX、XLSX、HTML、EPUB。可一次选择多个文件批量转换，并在下方下载结果。
"""
)

with st.sidebar:
    st.header("转换设置")
    in_files = st.file_uploader(
        "上传文件（可多选）:",
        type=[
            "pdf",
            "png",
            "jpg",
            "jpeg",
            "gif",
            "webp",
            "pptx",
            "docx",
            "xlsx",
            "html",
            "epub",
        ],
        accept_multiple_files=True,
    )
    output_format = st.selectbox(
        "输出格式", ["markdown", "json", "html", "chunks"], index=0
    )
    mode = st.selectbox(
        "模式",
        ["auto", "balanced", "fast"],
        index=0,
        help="auto：GPU 上自动使用 balanced；balanced：质量最高；fast：速度更快。",
    )
    page_range = st.text_input(
        "页码范围（可留空）",
        value="",
        help="例如 0,5-10,20。留空表示转换全部页面。",
    )
    use_llm = st.checkbox(
        "使用 LLM（需配置 API）", value=False, help="DeepSeek 配置见 README 第十章。"
    )
    with st.expander("高级选项"):
        force_ocr = st.checkbox("强制 OCR（扫描件适用）", value=False)
        disable_ocr = st.checkbox("禁用 OCR", value=False)
        strip_existing_ocr = st.checkbox("移除已有 OCR 文本并重新识别", value=False)
        keep_headers_footers = st.checkbox("保留页眉页脚", value=False)
        debug = st.checkbox("调试信息", value=False)
    run_marker = st.button("开始转换", type="primary", use_container_width=True)

    results = st.session_state.marker_results
    if results:
        if st.button("清空结果", use_container_width=True):
            st.session_state.marker_results = {}
            st.rerun()

if not in_files:
    st.info("请在左侧上传一个或多个文件。")
    st.stop()

single_mode = len(in_files) == 1

if run_marker:
    reset_failed(st.session_state.marker_results)
    progress = st.progress(0.0, text="准备中...")
    status = st.empty()

    cli_options.update(
        {
            "output_format": output_format,
            "page_range": page_range or None,
            "force_ocr": force_ocr,
            "disable_ocr": disable_ocr,
            "debug": debug,
            "output_dir": settings.DEBUG_DATA_FOLDER if debug else None,
            "use_llm": use_llm,
            "strip_existing_ocr": strip_existing_ocr,
            "keep_pageheader_in_output": keep_headers_footers,
            "keep_pagefooter_in_output": keep_headers_footers,
            "mode": None if mode == "auto" else mode,
        }
    )

    for idx, uploaded in enumerate(in_files):
        status.write(f"正在转换：{uploaded.name}（{idx + 1}/{len(in_files)}）")
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                input_path = prepare_input(uploaded, tmp_dir)
                config_parser = ConfigParser(cli_options)
                rendered = convert_file(input_path, config_parser, model_dict)
                text, ext, images = text_from_rendered(rendered)
            st.session_state.marker_results[uploaded.name] = {
                "text": text,
                "ext": ext,
                "images": images,
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001 - show the real error in the UI
            st.session_state.marker_results[uploaded.name] = {
                "text": "",
                "ext": "md",
                "images": {},
                "error": str(exc),
            }
        progress.progress((idx + 1) / len(in_files))

    progress.empty()
    status.empty()
    st.rerun()

results = st.session_state.marker_results
names = [f.name for f in in_files]
done = [n for n in names if n in results and not results[n].get("error")]
failed = [n for n in names if n in results and results[n].get("error")]

if failed:
    for name in failed:
        st.error(f"{name} 转换失败：{results[name]['error']}")

if not done:
    st.info("设置好参数后，点击左侧“开始转换”。")
    st.stop()

# ---------------- Batch download ----------------
if len(done) > 1:
    batch_buf = io.BytesIO()
    with zipfile.ZipFile(batch_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in done:
            item = results[name]
            zf.writestr(
                f"{os.path.splitext(name)[0]}/{os.path.splitext(name)[0]}.{item['ext']}",
                item["text"],
            )
            for img_name, img in (item["images"] or {}).items():
                img_buf = io.BytesIO()
                img.save(img_buf, format=settings.OUTPUT_IMAGE_FORMAT)
                zf.writestr(
                    f"{os.path.splitext(name)[0]}/{img_name}", img_buf.getvalue()
                )
    st.download_button(
        f"⬇ 打包下载全部结果（{len(done)} 个文件）",
        data=batch_buf.getvalue(),
        file_name="marker_results.zip",
        mime="application/zip",
        type="primary",
    )

if len(in_files) > 1:
    preview_name = st.selectbox("选择要预览的文件", done)
else:
    preview_name = done[0]

item = results[preview_name]
text = item["text"]
ext = item["ext"]
images = item["images"]

left, right = st.columns([0.5, 0.5])

with left:
    uploaded = next(f for f in in_files if f.name == preview_name)
    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            preview_pdf = prepare_input(uploaded, tmp_dir)
            pages = page_count(uploaded)
            if single_mode:
                page_number = st.number_input(
                    f"页码（共 {pages + 1} 页）", min_value=0, value=0, max_value=pages
                )
            else:
                page_number = st.number_input(
                    f"{preview_name} 页码（共 {pages + 1} 页）",
                    min_value=0,
                    value=0,
                    max_value=pages,
                    key=f"page_{preview_name}",
                )
            st.image(
                get_page_image(uploaded, page_number),
                caption=f"{preview_name} 第 {page_number + 1} 页",
                use_container_width=True,
            )
        except Exception as exc:  # noqa: BLE001
            st.warning(f"无法预览该文件：{exc}")

with right:
    st.download_button(
        f"⬇ 下载 {preview_name}（.{ext}）",
        data=text,
        file_name=f"{os.path.splitext(preview_name)[0]}.{ext}",
        mime={
            "md": "text/markdown",
            "html": "text/html",
            "json": "application/json",
        }.get(ext, "text/plain"),
    )
    if output_format == "markdown":
        st.markdown(markdown_insert_images(text, images), unsafe_allow_html=True)
    elif output_format == "json":
        st.json(text)
    elif output_format == "html":
        st.html(text)
    elif output_format == "chunks":
        st.json(text)

    if debug:
        st.write("原始输出：")
        st.code(text, language=output_format)

