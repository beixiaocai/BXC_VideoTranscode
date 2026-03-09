# BXC_VideoTranscode

一款基于 Python 和 FFmpeg 开发的图形化视频转码工具，支持多文件批量并发处理。

**当前版本: v1.0**

## 功能特性

- **多文件并发转码** - 支持1-8个线程同时处理多个视频文件
- **硬件加速** - 支持 NVIDIA NVENC 和 Intel QSV 硬件编码
- **实时进度监控** - 显示每个文件的转码进度、状态和耗时
- **参数自定义** - 灵活配置视频/音频编码参数

## 支持的编码器

| 类型 | 编码器 |
|------|--------|
| 视频软件编码 | libx264, libx265, mpeg4, libvpx-vp9 |
| 视频硬件编码 | h264_nvenc, hevc_nvenc, h264_qsv, hevc_qsv |
| 视频直通 | copy (不重新编码) |
| 音频编码 | aac, mp3, libopus, libvorbis, copy |

## 快速开始

### 环境要求
- Windows 7/8/10/11
- Python 3.8+

### 安装运行

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt

# 运行程序
python main.py
```

### 打包发布

```bash
pyinstaller main.spec
```

打包后的可执行文件位于 `dist/BXC_VideoTranscode.exe`

## 项目结构

```
BXC_VideoTranscode/
├── bin/                    # FFmpeg 工具目录
│   ├── ffmpeg.exe
│   ├── ffplay.exe
│   └── ffprobe.exe
├── main.py                 # 主程序
├── main.spec               # PyInstaller 打包配置
├── requirements.txt        # 依赖列表
└── logo.png                # 程序图标
```

## 开源地址

- **GitHub**: https://github.com/beixiaocai/BXC_VideoTranscode
- **Gitee**: https://gitee.com/Vanishi
- **Bilibili**: https://space.bilibili.com/487906612

## 开源协议

[MIT License](LICENSE)
