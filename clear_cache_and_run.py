#!/usr/bin/env python
"""
清除缓存并运行xtquantai
"""
import os
import shutil
import subprocess
import sys

def clear_cache():
    """
    清除uv包管理器的缓存目录。

    此函数会检查多个常见位置的uv缓存目录并将其删除。
    """
    cache_dir = os.path.expanduser("~/.local/share/uv")
    if os.path.exists(cache_dir):
        print(f"清除缓存目录: {cache_dir}")
        shutil.rmtree(cache_dir, ignore_errors=True)
    
    cache_dir = os.path.expanduser("~/.cache/uv")
    if os.path.exists(cache_dir):
        print(f"清除缓存目录: {cache_dir}")
        shutil.rmtree(cache_dir, ignore_errors=True)
    
    cache_dir = os.path.expanduser("~/AppData/Local/uv/cache")
    if os.path.exists(cache_dir):
        print(f"清除缓存目录: {cache_dir}")
        shutil.rmtree(cache_dir, ignore_errors=True)

def install_dependencies():
    """
    安装项目依赖项。

    此函数使用`uv`（如果可用）或`pip`来安装`anyio`模块和
    可编辑模式下的`xtquantai`包。
    """
    print("安装anyio模块...")
    try:
        # 尝试使用uv安装
        subprocess.run(["uv", "pip", "install", "anyio"], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        try:
            # 如果uv不可用，尝试使用pip
            subprocess.run([sys.executable, "-m", "pip", "install", "anyio"], check=True)
        except subprocess.CalledProcessError:
            print("警告: 无法安装anyio模块，某些功能可能无法正常工作")
    
    print("安装xtquantai包...")
    try:
        # 尝试使用uv安装
        subprocess.run(["uv", "pip", "install", "-e", "."], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        try:
            # 如果uv不可用，尝试使用pip
            subprocess.run([sys.executable, "-m", "pip", "install", "-e", "."], check=True)
        except subprocess.CalledProcessError:
            print("警告: 无法安装xtquantai包，某些功能可能无法正常工作")

def run_xtquantai():
    """
    运行xtquantai服务器。

    此函数将当前目录添加到Python路径，重新加载`xtquantai`模块
    以确保应用了更改，然后调用其`main`函数。
    """
    print("运行xtquantai...")
    # 添加当前目录到Python路径
    sys.path.insert(0, os.path.abspath('.'))
    
    # 清除可能的缓存
    import importlib
    try:
        import xtquantai
        importlib.reload(xtquantai)
        
        # 运行xtquantai
        xtquantai.main()
    except ImportError:
        print("错误: 无法导入xtquantai模块")
    except Exception as e:
        print(f"错误: {str(e)}")

if __name__ == "__main__":
    clear_cache()
    install_dependencies()
    run_xtquantai() 