import asyncio
from typing import Optional, List, Dict, Any
import json
import sys
import os
import traceback
import time

from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from pydantic import AnyUrl, BaseModel
import mcp.server.stdio

# 添加可能的xtquant模块路径
possible_paths = [
    os.path.expanduser("~/.local/lib/python3.11/site-packages"),
    os.path.expanduser("~/AppData/Local/Programs/Python/Python311/Lib/site-packages"),
    os.path.expanduser("~/AppData/Local/Programs/Python/Python311/Scripts"),
    os.path.expanduser("~/.local/bin"),
    os.path.expanduser("~/anaconda3/lib/python3.11/site-packages"),
    os.path.expanduser("~/miniconda3/lib/python3.11/site-packages"),
    os.path.expanduser("~/.venv/lib/python3.11/site-packages"),
    os.path.expanduser("~/venv/lib/python3.11/site-packages"),
    os.path.expanduser("~/.pyenv/versions/3.11/lib/python3.11/site-packages"),
]

# for path in possible_paths:
#     if path not in sys.path and os.path.exists(path):
#         sys.path.append(path)
#         print(f"添加路径到Python搜索路径: {path}")

# 导入xtquant相关模块
xtdata = None
UIPanel = None

try:
    from xtquant import xtdata
    print(f"成功导入xtquant模块，路径: {xtdata.__file__ if hasattr(xtdata, '__file__') else '未知'}")
    
    # 尝试导入UIPanel，如果不存在则创建一个模拟的UIPanel类
    try:
        from xtquant.xtdata import UIPanel
        print("成功导入UIPanel类")
    except ImportError as e:
        print(f"警告: 无法导入UIPanel类: {str(e)}")
        # 创建一个模拟的UIPanel类
        class UIPanel:
            def __init__(self, stock, period, figures=None):
                self.stock = stock
                self.period = period
                self.figures = figures or []
            
            def __str__(self):
                return f"UIPanel(stock={self.stock}, period={self.period}, figures={self.figures})"
except ImportError as e:
    print(f"警告: 无法导入xtquant模块: {str(e)}")
    print("Python搜索路径:")
    for path in sys.path:
        print(f"  - {path}")
    
    # 尝试创建模拟的xtdata模块
    class MockXtdata:
        def __init__(self):
            self.name = "MockXtdata"
        
        def get_trading_dates(self, market="SH"):
            print(f"模拟调用get_trading_dates({market})")
            return ["2023-01-01", "2023-01-02", "2023-01-03"]
        
        def get_stock_list_in_sector(self, sector="沪深A股"):
            print(f"模拟调用get_stock_list_in_sector({sector})")
            return ["000001.SZ", "600519.SH", "300059.SZ"]
        
        def get_instrument_detail(self, code, iscomplete=False):
            print(f"模拟调用get_instrument_detail({code}, {iscomplete})")
            return {"code": code, "name": "模拟股票", "price": 100.0}
        
        def apply_ui_panel_control(self, panels):
            print(f"模拟调用apply_ui_panel_control({panels})")
            return True
        
        def get_market_data(self, fields, stock_list, period="1d", start_time="", end_time="", count=-1, dividend_type="none", fill_data=True):
            print(f"模拟调用get_market_data({fields}, {stock_list}, {period}, {start_time}, {end_time}, {count}, {dividend_type}, {fill_data})")
            # 创建模拟数据
            result = {}
            for stock in stock_list:
                stock_data = {}
                for field in fields:
                    if field == "close":
                        stock_data[field] = [100.0, 101.0, 102.0]
                    elif field == "open":
                        stock_data[field] = [99.0, 100.0, 101.0]
                    elif field == "high":
                        stock_data[field] = [102.0, 103.0, 104.0]
                    elif field == "low":
                        stock_data[field] = [98.0, 99.0, 100.0]
                    elif field == "volume":
                        stock_data[field] = [10000, 12000, 15000]
                    else:
                        stock_data[field] = [0.0, 0.0, 0.0]
                result[stock] = stock_data
            return result
    
    xtdata = MockXtdata()
    
    # 创建一个模拟的UIPanel类
    class UIPanel:
        def __init__(self, stock, period, figures=None):
            self.stock = stock
            self.period = period
            self.figures = figures or []
        
        def __str__(self):
            return f"UIPanel(stock={self.stock}, period={self.period}, figures={self.figures})"

# Initialize XTQuant data service
xtdc_initialized = False

server = Server("xtquantai")

def ensure_xtdc_initialized():
    """
    确保XTQuant数据中心已初始化。

    该函数检查`xtdc_initialized`全局变量。如果尚未初始化，
    它会尝试通过调用`xtdata.start_xtdata()`（如果存在）来启动XTQuant数据中心，
    并将`xtdc_initialized`设置为True。如果初始化失败，则会打印错误消息。
    """
    global xtdc_initialized
    if not xtdc_initialized:
        try:
            # 尝试初始化xtquant
            if hasattr(xtdata, 'start_xtdata'):
                xtdata.start_xtdata()
            xtdc_initialized = True
            print("XTQuant数据中心已初始化")
        except Exception as e:
            print(f"初始化XTQuant数据中心失败: {str(e)}")
            traceback.print_exc()

# 定义工具输入和输出模型
class GetTradingDatesInput(BaseModel):
    market: str = "SH"  # 默认为上海市场

class GetStockListInput(BaseModel):
    sector: str = "沪深A股"  # 默认为沪深A股

class GetInstrumentDetailInput(BaseModel):
    code: str  # 股票代码，例如 "000001.SZ"
    iscomplete: bool = False  # 是否获取全部字段，默认为False

# 定义新的输入模型
class GetMarketDataInput(BaseModel):
    codes: str  # 股票代码列表，用逗号分隔，例如 "000001.SZ,600519.SH"
    period: str = "1d"  # 周期，例如 "1d", "1m", "5m" 等
    start_date: str = ""  # 开始日期，格式为 "YYYYMMDD"
    end_date: str = ""  # 结束日期，格式为 "YYYYMMDD"，为空表示当前日期
    fields: str = ""  # 字段列表，用逗号分隔，为空表示所有字段

# 创建图表面板输入模型
class CreateChartPanelInput(BaseModel):
    codes: str  # 股票代码列表，用逗号分隔，例如 "000001.SZ,600519.SH"
    period: str = "1d"  # 周期，例如 "1d", "1m", "5m" 等
    indicators: str = "ma"  # 指标名称，例如 "ma", "macd", "kdj" 等
    params: str = "5,10,20"  # 指标参数，用逗号分隔，例如 "5,10,20"

# 新增: 创建自定义布局输入模型
class CreateCustomLayoutInput(BaseModel):
    codes: str  # 股票代码列表，用逗号分隔，例如 "000001.SZ,600519.SH"
    period: str = "1d"  # 周期，例如 "1d", "1m", "5m" 等
    indicator_name: str = "ma"  # 指标名称，例如 "ma", "macd", "kdj" 等
    param_names: str = "n1,n2,n3"  # 参数名称，用逗号分隔，例如 "n1,n2,n3"
    param_values: str = "5,10,20"  # 参数值，用逗号分隔，例如 "5,10,20"

@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """
    列出可用资源。

    此函数目前返回一个空列表，因为此服务器中没有定义资源。

    Returns:
        一个空的资源列表。
    """
    return []

@server.read_resource()
async def handle_read_resource(uri: AnyUrl) -> str:
    """
    读取特定资源。

    此函数目前会引发`ValueError`，因为不支持任何资源URI。

    Args:
        uri: 要读取的资源的URI。

    Returns:
        资源的字符串内容。

    Raises:
        ValueError: 如果URI不受支持。
    """
    raise ValueError(f"Unsupported URI: {uri}")

@server.list_prompts()
async def handle_list_prompts() -> list[types.Prompt]:
    """
    列出可用提示。

    此函数目前返回一个空列表，因为此服务器中没有定义提示。

    Returns:
        一个空的提示列表。
    """
    return []

@server.get_prompt()
async def handle_get_prompt(
    name: str, arguments: dict[str, str] | None
) -> types.GetPromptResult:
    """
    获取特定提示。

    此函数目前会引发`ValueError`，因为没有已知的提示。

    Args:
        name: 要获取的提示的名称。
        arguments: 提示的参数。

    Returns:
        获取提示的结果。

    Raises:
        ValueError: 如果提示名称未知。
    """
    raise ValueError(f"Unknown prompt: {name}")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    列出所有可用工具。

    此函数向MCP客户端提供可用工具的列表，包括其名称、描述和输入模式。

    Returns:
        一个`types.Tool`对象列表，描述每个可用工具。
    """
    print("handle_list_tools被调用，返回所有工具")
    tools = [
        types.Tool(
            name="get_trading_dates",
            description="获取指定市场的交易日期列表",
            inputSchema={
                "type": "object",
                "properties": {
                    "market": {
                        "type": "string",
                        "description": "市场代码，例如 SH 表示上海市场",
                        "default": "SH"
                    }
                }
            }
        ),
        types.Tool(
            name="get_stock_list",
            description="获取指定板块的股票列表",
            inputSchema={
                "type": "object",
                "properties": {
                    "sector": {
                        "type": "string",
                        "description": "板块名称，例如 沪深A股",
                        "default": "沪深A股"
                    }
                }
            }
        ),
        types.Tool(
            name="get_instrument_detail",
            description="获取指定股票的详细信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "股票代码，例如 000001.SZ"
                    },
                    "iscomplete": {
                        "type": "boolean",
                        "description": "是否获取全部字段，默认为False",
                        "default": False
                    }
                },
                "required": ["code"]
            }
        ),
        types.Tool(
            name="get_history_market_data",
            description="获取历史行情数据",
            inputSchema={
                "type": "object",
                "properties": {
                    "codes": {
                        "type": "string",
                        "description": "股票代码列表，用逗号分隔，例如 \"000001.SZ,600519.SH\""
                    },
                    "period": {
                        "type": "string",
                        "description": "周期，例如 \"1d\", \"1m\", \"5m\" 等",
                        "default": "1d"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "开始日期，格式为 \"YYYYMMDD\"",
                        "default": ""
                    },
                    "end_date": {
                        "type": "string",
                        "description": "结束日期，格式为 \"YYYYMMDD\"，为空表示当前日期",
                        "default": ""
                    },
                    "fields": {
                        "type": "string",
                        "description": "字段列表，用逗号分隔，为空表示所有字段",
                        "default": ""
                    }
                },
                "required": ["codes"]
            }
        ),
        types.Tool(
            name="get_latest_market_data",
            description="获取最新行情数据",
            inputSchema={
                "type": "object",
                "properties": {
                    "codes": {
                        "type": "string",
                        "description": "股票代码列表，用逗号分隔，例如 \"000001.SZ,600519.SH\""
                    },
                    "period": {
                        "type": "string",
                        "description": "周期，例如 \"1d\", \"1m\", \"5m\" 等",
                        "default": "1d"
                    }
                },
                "required": ["codes"]
            }
        ),
        types.Tool(
            name="get_full_market_data",
            description="获取历史+最新行情数据",
            inputSchema={
                "type": "object",
                "properties": {
                    "codes": {
                        "type": "string",
                        "description": "股票代码列表，用逗号分隔，例如 \"000001.SZ,600519.SH\""
                    },
                    "period": {
                        "type": "string",
                        "description": "周期，例如 \"1d\", \"1m\", \"5m\" 等",
                        "default": "1d"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "开始日期，格式为 \"YYYYMMDD\"",
                        "default": ""
                    },
                    "end_date": {
                        "type": "string",
                        "description": "结束日期，格式为 \"YYYYMMDD\"，为空表示当前日期",
                        "default": ""
                    },
                    "fields": {
                        "type": "string",
                        "description": "字段列表，用逗号分隔，为空表示所有字段",
                        "default": ""
                    }
                },
                "required": ["codes"]
            }
        ),
        types.Tool(
            name="create_chart_panel",
            description="创建图表面板，显示指定股票的技术指标",
            inputSchema={
                "type": "object",
                "properties": {
                    "codes": {
                        "type": "string",
                        "description": "股票代码列表，用逗号分隔，例如 000001.SZ,600519.SH"
                    },
                    "period": {
                        "type": "string",
                        "description": "周期，例如 1d, 1m, 5m 等",
                        "default": "1d"
                    },
                    "indicators": {
                        "type": "string",
                        "description": "指标名称，例如 ma, macd, kdj 等",
                        "default": "ma"
                    },
                    "params": {
                        "type": "string",
                        "description": "指标参数，用逗号分隔，例如 5,10,20",
                        "default": "5,10,20"
                    }
                },
                "required": ["codes"]
            }
        ),
        types.Tool(
            name="create_custom_layout",
            description="创建自定义布局，可以指定指标名称、参数名和参数值",
            inputSchema={
                "type": "object",
                "properties": {
                    "codes": {
                        "type": "string",
                        "description": "股票代码列表，用逗号分隔，例如 000001.SZ,600519.SH"
                    },
                    "period": {
                        "type": "string",
                        "description": "周期，例如 1d, 1m, 5m 等",
                        "default": "1d"
                    },
                    "indicator_name": {
                        "type": "string",
                        "description": "指标名称，例如 ma, macd, kdj 等",
                        "default": "ma"
                    },
                    "param_names": {
                        "type": "string",
                        "description": "参数名称，用逗号分隔，例如 n1,n2,n3 或 short,long,mid",
                        "default": "n1,n2,n3"
                    },
                    "param_values": {
                        "type": "string",
                        "description": "参数值，用逗号分隔，例如 5,10,20",
                        "default": "5,10,20"
                    }
                },
                "required": ["codes"]
            }
        )
    ]
    print(f"返回的工具数量: {len(tools)}")
    return tools

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    调用特定的工具。

    此函数根据提供的名称和参数执行工具。它将参数路由到适当的工具实现函数，
    并以MCP客户端可以使用的格式返回结果。

    Args:
        name: 要调用的工具的名称。
        arguments: 工具的参数字典。

    Returns:
        内容对象列表，表示工具执行的结果。

    Raises:
        ValueError: 如果工具名称未知。
    """
    if name == "get_trading_dates":
        market = "SH"
        if arguments and "market" in arguments:
            market = arguments["market"]
        
        input_model = GetTradingDatesInput(market=market)
        result = await get_trading_dates(input_model)
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "get_stock_list":
        sector = "沪深A股"
        if arguments and "sector" in arguments:
            sector = arguments["sector"]
        
        input_model = GetStockListInput(sector=sector)
        result = await get_stock_list(input_model)
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "get_instrument_detail":
        if not arguments or "code" not in arguments:
            return [types.TextContent(type="text", text="错误: 缺少必要参数 'code'")]
        
        code = arguments["code"]
        # 从参数中获取iscomplete，如果不存在则默认为False
        iscomplete = False
        if arguments and "iscomplete" in arguments:
            # 确保iscomplete是布尔值
            if isinstance(arguments["iscomplete"], bool):
                iscomplete = arguments["iscomplete"]
            elif isinstance(arguments["iscomplete"], str):
                iscomplete = arguments["iscomplete"].lower() == "true"
        
        input_model = GetInstrumentDetailInput(code=code, iscomplete=iscomplete)
        result = await get_instrument_detail(input_model)
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "get_history_market_data":
        if not arguments or "codes" not in arguments:
            return [types.TextContent(type="text", text="错误: 缺少必要参数 'codes'")]
        
        # 处理字符串格式的codes参数
        codes_str = arguments["codes"]
        codes = [code.strip() for code in codes_str.split(",") if code.strip()]
        
        period = arguments.get("period", "1d")
        start_date = arguments.get("start_date", "")
        end_date = arguments.get("end_date", "")
        
        # 处理字符串格式的fields参数
        fields_str = arguments.get("fields", "")
        fields = [field.strip() for field in fields_str.split(",") if field.strip()]
        
        input_model = GetMarketDataInput(codes=codes_str, period=period, start_date=start_date, end_date=end_date, fields=fields_str)
        result = await get_history_market_data(input_model)
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "get_latest_market_data":
        if not arguments or "codes" not in arguments:
            return [types.TextContent(type="text", text="错误: 缺少必要参数 'codes'")]
        
        # 处理字符串格式的codes参数
        codes_str = arguments["codes"]
        codes = [code.strip() for code in codes_str.split(",") if code.strip()]
        
        period = arguments.get("period", "1d")
        
        input_model = GetMarketDataInput(codes=codes_str, period=period)
        result = await get_latest_market_data(input_model)
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "get_full_market_data":
        if not arguments or "codes" not in arguments:
            return [types.TextContent(type="text", text="错误: 缺少必要参数 'codes'")]
        
        # 处理字符串格式的codes参数
        codes_str = arguments["codes"]
        codes = [code.strip() for code in codes_str.split(",") if code.strip()]
        
        period = arguments.get("period", "1d")
        start_date = arguments.get("start_date", "")
        end_date = arguments.get("end_date", "")
        
        # 处理字符串格式的fields参数
        fields_str = arguments.get("fields", "")
        fields = [field.strip() for field in fields_str.split(",") if field.strip()]
        
        input_model = GetMarketDataInput(codes=codes_str, period=period, start_date=start_date, end_date=end_date, fields=fields_str)
        result = await get_full_market_data(input_model)
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    elif name == "create_chart_panel":
        # 如果没有提供参数，使用默认值
        if not arguments:
            arguments = {}
        
        # 如果没有提供codes参数，使用默认值
        if "codes" not in arguments or not arguments["codes"]:
            # 获取沪深A股前5只股票作为默认值
            try:
                stock_list_input = GetStockListInput(sector="沪深A股")
                stock_list = await get_stock_list(stock_list_input)
                if isinstance(stock_list, list) and len(stock_list) > 0:
                    # 只取前5只股票
                    default_codes = ",".join(stock_list[:5])
                else:
                    default_codes = "000001.SZ,600519.SH"  # 默认平安银行和贵州茅台
            except Exception:
                default_codes = "000001.SZ,600519.SH"  # 默认平安银行和贵州茅台
            
            arguments["codes"] = default_codes
            print(f"未提供codes参数，使用默认值: {default_codes}")
        
        codes = arguments["codes"]
        period = arguments.get("period", "1d")
        indicators = arguments.get("indicators", "ma")
        params = arguments.get("params", "5,10,20")
        
        input_model = CreateChartPanelInput(
            codes=codes,
            period=period,
            indicators=indicators,
            params=params
        )
        result = await create_chart_panel(input_model)
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    # 新增: 处理创建自定义布局工具
    elif name == "create_custom_layout":
        # 如果没有提供参数，使用默认值
        if not arguments:
            arguments = {}
        
        # 如果没有提供codes参数，使用默认值
        if "codes" not in arguments or not arguments["codes"]:
            # 获取沪深A股前5只股票作为默认值
            try:
                stock_list_input = GetStockListInput(sector="沪深A股")
                stock_list = await get_stock_list(stock_list_input)
                if isinstance(stock_list, list) and len(stock_list) > 0:
                    # 只取前5只股票
                    default_codes = ",".join(stock_list[:5])
                else:
                    default_codes = "000001.SZ,600519.SH"  # 默认平安银行和贵州茅台
            except Exception:
                default_codes = "000001.SZ,600519.SH"  # 默认平安银行和贵州茅台
            
            arguments["codes"] = default_codes
            print(f"未提供codes参数，使用默认值: {default_codes}")
        
        codes = arguments["codes"]
        period = arguments.get("period", "1d")
        indicator_name = arguments.get("indicator_name", "ma")
        param_names = arguments.get("param_names", "n1,n2,n3")
        param_values = arguments.get("param_values", "5,10,20")
        
        input_model = CreateCustomLayoutInput(
            codes=codes,
            period=period,
            indicator_name=indicator_name,
            param_names=param_names,
            param_values=param_values
        )
        result = await create_custom_layout(input_model)
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    else:
        raise ValueError(f"Unknown tool: {name}")

# 工具函数实现，不使用装饰器
async def get_trading_dates(input: GetTradingDatesInput) -> List[str]:
    """
    获取指定市场的交易日期列表。

    Args:
        input: 包含`market`参数的输入模型。
            market: 市场代码 (例如, "SH" 代表上海市场)。

    Returns:
        字符串列表，表示指定市场的交易日期。
        如果出错则返回包含错误信息的列表。
    """
    try:
        # 确保XTQuant数据中心已初始化
        ensure_xtdc_initialized()
        
        if xtdata is None:
            return ["错误: xtdata模块未正确加载"]
            
        print(f"调用xtdata.get_trading_dates({input.market})")
        trading_dates = xtdata.get_trading_dates(input.market)
        
        # 检查返回值
        if trading_dates is None or len(trading_dates) == 0:
            return ["未找到交易日期数据"]
            
        # 只返回最近30个交易日
        recent_dates = trading_dates[-30:] if len(trading_dates) > 30 else trading_dates
        
        # 处理整数格式的日期
        formatted_dates = []
        for date in recent_dates:
            if isinstance(date, int):
                # 假设日期格式为YYYYMMDD的整数
                date_str = str(date)
                if len(date_str) == 8:
                    formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                    formatted_dates.append(formatted_date)
                else:
                    formatted_dates.append(str(date))
            else:
                # 尝试使用strftime，如果是日期对象
                try:
                    formatted_dates.append(date.strftime("%Y-%m-%d"))
                except AttributeError:
                    formatted_dates.append(str(date))
        
        return formatted_dates
    except Exception as e:
        print(f"获取交易日期出错: {str(e)}")
        traceback.print_exc()
        return [f"错误: {str(e)}"]

async def get_stock_list(input: GetStockListInput) -> List[str]:
    """
    获取指定板块的股票列表。

    Args:
        input: 包含`sector`参数的输入模型。
            sector: 板块名称 (例如, "沪深A股")。

    Returns:
        字符串列表，表示指定板块的股票代码。
        如果出错则返回包含错误信息的列表。
    """
    try:
        # 确保XTQuant数据中心已初始化
        ensure_xtdc_initialized()
        
        if xtdata is None:
            return ["错误: xtdata模块未正确加载"]
            
        print(f"调用xtdata.get_stock_list_in_sector({input.sector})")
        stock_list = xtdata.get_stock_list_in_sector(input.sector)
        
        # 检查返回值
        if stock_list is None or len(stock_list) == 0:
            return [f"未找到板块 {input.sector} 的股票列表"]
            
        # 只返回前50个股票代码
        limited_list = stock_list[:50] if len(stock_list) > 50 else stock_list
        return limited_list
    except Exception as e:
        print(f"获取股票列表出错: {str(e)}")
        traceback.print_exc()
        return [f"错误: {str(e)}"]

async def get_instrument_detail(input: GetInstrumentDetailInput) -> Dict[str, Any]:
    """
    获取指定股票的详细信息。

    Args:
        input: 包含`code`和`iscomplete`参数的输入模型。
            code: 股票代码 (例如, "000001.SZ")。
            iscomplete: 是否获取完整数据 (默认为 False)。

    Returns:
        包含股票详细信息的字典。
        如果出错则返回包含错误信息的字典。
    """
    try:
        # 确保XTQuant数据中心已初始化
        ensure_xtdc_initialized()
        
        if xtdata is None:
            return {"error": "xtdata模块未正确加载"}
            
        print(f"调用xtdata.get_instrument_detail({input.code}, {input.iscomplete})")
        # 直接使用用户输入的股票代码，不做任何格式处理
        detail = xtdata.get_instrument_detail(input.code, input.iscomplete)
        
        # 处理返回值为None的情况
        if detail is None:
            return {"message": f"未找到股票代码 {input.code} 的详细信息"}
            
        # 将结果转换为可序列化的字典
        result = {}
        for key, value in detail.items():
            if isinstance(value, (str, int, float, bool, type(None))):
                result[key] = value
            else:
                result[key] = str(value)
        
        return result
    except Exception as e:
        print(f"获取股票详情出错: {str(e)}")
        traceback.print_exc()
        return {"error": str(e)}

# 新增的工具函数实现
async def get_history_market_data(input: GetMarketDataInput) -> Dict[str, Any]:
    """
    获取历史行情数据。

    Args:
        input: 包含市场数据请求参数的输入模型。
            codes: 以逗号分隔的股票代码字符串 (例如, "000001.SZ,600519.SH")。
            period: 数据周期 (例如, "1d", "1m", "5m")。
            start_date: 开始日期 "YYYYMMDD"。
            end_date: 结束日期 "YYYYMMDD"。
            fields: 以逗号分隔的字段列表。

    Returns:
        包含历史市场数据的字典。
        如果出错则返回包含错误信息的字典。
    """
    try:
        # 确保XTQuant数据中心已初始化
        ensure_xtdc_initialized()
        
        if xtdata is None:
            return {"error": "xtdata模块未正确加载"}
        
        # 解析股票代码列表
        codes = [code.strip() for code in input.codes.split(",") if code.strip()]
        if not codes:
            return {"error": "未提供有效的股票代码"}
        
        # 解析字段列表
        fields = []
        if input.fields:
            fields = [field.strip() for field in input.fields.split(",") if field.strip()]
        
        # 如果未指定字段，使用默认字段
        if not fields:
            fields = ["open", "high", "low", "close", "volume"]
        
        print(f"获取历史行情数据: 股票={codes}, 周期={input.period}, 字段={fields}, 开始日期={input.start_date}, 结束日期={input.end_date}")
        
        try:
            # 获取历史行情数据
            print(f"调用xtdata.get_market_data({fields}, {codes}, {input.period}, {input.start_date}, {input.end_date})")
            data = xtdata.get_market_data(fields, codes, period=input.period, 
                                          start_time=input.start_date, end_time=input.end_date)
            
            # 处理返回值
            if data is None:
                return {"error": "获取历史行情数据失败"}
            
            # 将数据转换为可序列化的格式
            result = {}
            for code, stock_data in data.items():
                code_result = {}
                for field, values in stock_data.items():
                    # 将numpy数组转换为列表
                    if hasattr(values, "tolist"):
                        code_result[field] = values.tolist()
                    else:
                        code_result[field] = list(values)
                result[code] = code_result
            
            return result
        except Exception as e:
            print(f"获取历史行情数据出错: {str(e)}")
            traceback.print_exc()
            return {"error": f"获取历史行情数据失败: {str(e)}"}
    except Exception as e:
        print(f"处理历史行情数据请求出错: {str(e)}")
        traceback.print_exc()
        return {"error": str(e)}

async def get_latest_market_data(input: GetMarketDataInput) -> Dict[str, Any]:
    """
    获取最新行情数据。

    Args:
        input: 包含市场数据请求参数的输入模型。
            codes: 以逗号分隔的股票代码字符串 (例如, "000001.SZ,600519.SH")。
            period: 数据周期 (例如, "1d", "1m", "5m")。

    Returns:
        包含最新市场数据的字典。
        如果出错则返回包含错误信息的字典。
    """
    try:
        # 确保XTQuant数据中心已初始化
        ensure_xtdc_initialized()
        
        if xtdata is None:
            return {"error": "xtdata模块未正确加载"}
        
        # 解析股票代码列表
        codes = [code.strip() for code in input.codes.split(",") if code.strip()]
        if not codes:
            return {"error": "未提供有效的股票代码"}
        
        # 过滤有效的股票代码
        valid_codes = []
        for code in codes:
            # 检查股票代码格式
            if "." in code and len(code) >= 6:
                valid_codes.append(code)
        
        if not valid_codes:
            return {"error": "未提供有效的股票代码"}
        
        print(f"获取最新行情数据: 股票={valid_codes}, 周期={input.period}")
        
        try:
            # 获取最新行情数据
            print(f"调用xtdata.get_market_data([], {valid_codes}, {input.period}, count=1)")
            data = xtdata.get_market_data(["open", "high", "low", "close", "volume"], valid_codes, period=input.period, count=1)
            
            # 处理返回值
            if data is None:
                return {"error": "获取最新行情数据失败"}
            
            # 将数据转换为可序列化的格式
            result = {}
            for code, stock_data in data.items():
                code_result = {}
                for field, values in stock_data.items():
                    # 将numpy数组转换为列表
                    if hasattr(values, "tolist"):
                        code_result[field] = values.tolist()
                    else:
                        code_result[field] = list(values)
                result[code] = code_result
            
            return result
        except Exception as e:
            print(f"获取最新行情数据出错: {str(e)}")
            traceback.print_exc()
            return {"error": f"获取最新行情数据失败: {str(e)}"}
    except Exception as e:
        print(f"处理最新行情数据请求出错: {str(e)}")
        traceback.print_exc()
        return {"error": str(e)}

async def get_full_market_data(input: GetMarketDataInput) -> Dict[str, Any]:
    """
    获取历史和最新行情数据。

    Args:
        input: 包含市场数据请求参数的输入模型。
            codes: 以逗号分隔的股票代码字符串 (例如, "000001.SZ,600519.SH")。
            period: 数据周期 (例如, "1d", "1m", "5m")。
            start_date: 开始日期 "YYYYMMDD"。
            end_date: 结束日期 "YYYYMMDD"。
            fields: 以逗号分隔的字段列表。

    Returns:
        包含历史和最新市场数据的字典。
        如果出错则返回包含错误信息的字典。
    """
    try:
        # 确保XTQuant数据中心已初始化
        ensure_xtdc_initialized()
        
        if xtdata is None:
            return {"error": "xtdata模块未正确加载"}
        
        # 解析股票代码列表
        codes = [code.strip() for code in input.codes.split(",") if code.strip()]
        if not codes:
            return {"error": "未提供有效的股票代码"}
        
        # 过滤有效的股票代码
        valid_codes = []
        for code in codes:
            # 检查股票代码格式
            if "." in code and len(code) >= 6:
                valid_codes.append(code)
        
        if not valid_codes:
            return {"error": "未提供有效的股票代码"}
        
        # 解析字段列表
        fields = []
        if input.fields:
            fields = [field.strip() for field in input.fields.split(",") if field.strip()]
        
        # 如果未指定字段，使用默认字段
        if not fields:
            fields = ["open", "high", "low", "close", "volume"]
        
        print(f"获取历史+最新行情数据: 股票={valid_codes}, 周期={input.period}, 字段={fields}, 开始日期={input.start_date}, 结束日期={input.end_date}")
        
        try:
            # 获取历史+最新行情数据
            print(f"调用xtdata.get_market_data({fields}, {valid_codes}, {input.period}, {input.start_date}, {input.end_date}, count=-1)")
            data = xtdata.get_market_data(fields, valid_codes, period=input.period, 
                                          start_time=input.start_date, end_time=input.end_date, count=-1)
            
            # 处理返回值
            if data is None:
                return {"error": "获取历史+最新行情数据失败"}
            
            # 将数据转换为可序列化的格式
            result = {}
            for code, stock_data in data.items():
                code_result = {}
                for field, values in stock_data.items():
                    # 将numpy数组转换为列表
                    if hasattr(values, "tolist"):
                        code_result[field] = values.tolist()
                    else:
                        code_result[field] = list(values)
                result[code] = code_result
            
            return result
        except Exception as e:
            print(f"获取历史+最新行情数据出错: {str(e)}")
            traceback.print_exc()
            return {"error": f"获取历史+最新行情数据失败: {str(e)}"}
    except Exception as e:
        print(f"处理历史+最新行情数据请求出错: {str(e)}")
        traceback.print_exc()
        return {"error": str(e)}

async def create_chart_panel(input: CreateChartPanelInput) -> Dict[str, Any]:
    """
    创建显示指定股票技术指标的图表面板。

    Args:
        input: 包含图表创建参数的输入模型。
            codes: 以逗号分隔的股票代码字符串。
            period: 数据周期。
            indicators: 以逗号分隔的技术指标列表。
            params: 以逗号分隔的指标参数。

    Returns:
        包含操作结果的字典，包括成功或失败消息以及调试信息。
    """
    try:
        # 确保XTQuant数据中心已初始化
        ensure_xtdc_initialized()
        
        # 收集环境信息
        env_info = {
            "python_version": sys.version,
            "platform": sys.platform,
            "cwd": os.getcwd(),
            "pid": os.getpid(),
            "user": os.environ.get("USERNAME", "unknown"),
            "xtdata_type": str(type(xtdata)),
            "xtdata_dir": dir(xtdata),
            "has_apply_ui_panel_control": hasattr(xtdata, 'apply_ui_panel_control'),
        }
        print(f"环境信息: {json.dumps(env_info, indent=2)}")
        
        if xtdata is None:
            return {"error": "xtdata模块未正确加载", "env_info": env_info}
        
        # 解析股票代码列表
        stock_list = [code.strip() for code in input.codes.split(",") if code.strip()]
        if not stock_list:
            return {"error": "未提供有效的股票代码", "env_info": env_info}
        
        # 解析指标参数
        indicator_params = [int(p.strip()) if p.strip().isdigit() else p.strip() 
                           for p in input.params.split(",") if p.strip()]
        
        # 构建指标配置
        indicator_config = {}
        if input.indicators == "ma":
            # 处理移动平均线指标
            ma_params = {}
            for i, param in enumerate(indicator_params, 1):
                ma_params[f'n{i}'] = param
            indicator_config = {'ma': ma_params}
        elif input.indicators == "macd":
            # 处理MACD指标
            if len(indicator_params) >= 3:
                indicator_config = {'macd': {'short': indicator_params[0], 
                                            'long': indicator_params[1], 
                                            'mid': indicator_params[2]}}
            else:
                indicator_config = {'macd': {}}  # 使用默认参数
        elif input.indicators == "kdj":
            # 处理KDJ指标
            if len(indicator_params) >= 3:
                indicator_config = {'kdj': {'n': indicator_params[0], 
                                           'm1': indicator_params[1], 
                                           'm2': indicator_params[2]}}
            else:
                indicator_config = {'kdj': {}}  # 使用默认参数
        else:
            # 其他指标，简单处理
            indicator_config = {input.indicators: {}}
        
        # 创建面板列表
        print(f"创建图表面板: 股票={stock_list}, 周期={input.period}, 指标={indicator_config}")
        
        panel_info = []
        try:
            # 尝试创建UIPanel对象
            panels = []
            for stock in stock_list:
                try:
                    panel = UIPanel(stock, input.period, figures=[indicator_config])
                    panels.append(panel)
                    panel_info.append({
                        "stock": stock,
                        "period": input.period,
                        "figures": str(indicator_config),
                        "panel_type": str(type(panel)),
                        "panel_str": str(panel)
                    })
                except Exception as e:
                    error_msg = f"创建UIPanel对象失败: {str(e)}"
                    print(error_msg)
                    traceback.print_exc()
                    # 如果创建UIPanel对象失败，使用字典代替
                    panel_dict = {
                        "stock": stock,
                        "period": input.period,
                        "figures": [indicator_config]
                    }
                    panels.append(panel_dict)
                    panel_info.append({
                        "stock": stock,
                        "period": input.period,
                        "figures": str(indicator_config),
                        "panel_type": "dict",
                        "error": str(e)
                    })
            
            # 应用面板控制
            print(f"调用xtdata.apply_ui_panel_control(panels)")
            
            method_results = {}
            # 检查apply_ui_panel_control方法是否存在
            if hasattr(xtdata, 'apply_ui_panel_control'):
                try:
                    start_time = time.time()
                    result = xtdata.apply_ui_panel_control(panels)
                    end_time = time.time()
                    method_results["apply_ui_panel_control"] = {
                        "result": str(result),
                        "time_taken": end_time - start_time
                    }
                    print(f"apply_ui_panel_control结果: {result}, 耗时: {end_time - start_time}秒")
                except Exception as e:
                    error_msg = f"调用apply_ui_panel_control出错: {str(e)}"
                    print(error_msg)
                    traceback.print_exc()
                    method_results["apply_ui_panel_control"] = {"error": str(e)}
            else:
                print("警告: xtdata模块没有apply_ui_panel_control方法")
                method_results["apply_ui_panel_control"] = {"exists": False}
                
                # 尝试其他可能的方法名
                possible_methods = ['apply_panel_control', 'create_panel', 'show_panel', 'display_panel']
                for method_name in possible_methods:
                    if hasattr(xtdata, method_name):
                        print(f"尝试使用替代方法: {method_name}")
                        try:
                            method = getattr(xtdata, method_name)
                            start_time = time.time()
                            result = method(panels)
                            end_time = time.time()
                            method_results[method_name] = {
                                "result": str(result),
                                "time_taken": end_time - start_time
                            }
                            print(f"{method_name}结果: {result}, 耗时: {end_time - start_time}秒")
                            break
                        except Exception as e:
                            error_msg = f"调用{method_name}出错: {str(e)}"
                            print(error_msg)
                            traceback.print_exc()
                            method_results[method_name] = {"error": str(e)}
                else:
                    print("无法找到合适的方法来显示图表面板")
                    method_results["no_method_found"] = True
            
            # 尝试强制刷新UI
            try:
                if hasattr(xtdata, 'refresh_ui'):
                    print("尝试调用refresh_ui方法")
                    xtdata.refresh_ui()
                    method_results["refresh_ui"] = {"called": True}
            except Exception as e:
                print(f"调用refresh_ui出错: {str(e)}")
                method_results["refresh_ui"] = {"error": str(e)}
            
            # 等待一段时间，确保UI有时间更新
            time.sleep(0.5)
            
            # 返回结果
            return {
                "success": True,
                "message": f"已成功创建 {len(stock_list)} 个图表面板",
                "details": {
                    "stocks": stock_list,
                    "period": input.period,
                    "indicator": input.indicators,
                    "parameters": indicator_params
                },
                "debug_info": {
                    "env_info": env_info,
                    "panel_info": panel_info,
                    "method_results": method_results
                }
            }
        except Exception as e:
            print(f"创建或应用面板时出错: {str(e)}")
            traceback.print_exc()
            return {
                "error": f"创建或应用面板时出错: {str(e)}",
                "debug_info": {
                    "env_info": env_info,
                    "panel_info": panel_info,
                    "traceback": traceback.format_exc()
                }
            }
    except Exception as e:
        print(f"创建图表面板出错: {str(e)}")
        traceback.print_exc()
        return {
            "error": str(e),
            "debug_info": {
                "traceback": traceback.format_exc()
            }
        }

# 新增: 创建自定义布局函数
async def create_custom_layout(input: CreateCustomLayoutInput) -> Dict[str, Any]:
    """
    创建自定义布局，允许指定指标名称、参数名称和参数值。

    Args:
        input: 包含自定义布局参数的输入模型。
            codes: 以逗号分隔的股票代码字符串。
            period: 数据周期。
            indicator_name: 技术指标的名称。
            param_names: 以逗号分隔的参数名称。
            param_values: 以逗号分隔的参数值。

    Returns:
        包含操作结果的字典，包括成功或失败消息以及调试信息。
    """
    try:
        # 确保XTQuant数据中心已初始化
        ensure_xtdc_initialized()
        
        # 收集环境信息
        env_info = {
            "python_version": sys.version,
            "platform": sys.platform,
            "cwd": os.getcwd(),
            "pid": os.getpid(),
            "user": os.environ.get("USERNAME", "unknown"),
            "xtdata_type": str(type(xtdata)),
            "xtdata_dir": dir(xtdata),
            "has_apply_ui_panel_control": hasattr(xtdata, 'apply_ui_panel_control'),
        }
        print(f"环境信息: {json.dumps(env_info, indent=2)}")
        
        if xtdata is None:
            return {"error": "xtdata模块未正确加载", "env_info": env_info}
        
        # 解析股票代码列表
        stock_list = [code.strip() for code in input.codes.split(",") if code.strip()]
        if not stock_list:
            return {"error": "未提供有效的股票代码", "env_info": env_info}
        
        # 解析参数名称
        param_names = [name.strip() for name in input.param_names.split(",") if name.strip()]
        
        # 解析参数值
        param_values = []
        for value in input.param_values.split(","):
            if value.strip():
                # 尝试将值转换为整数或浮点数
                try:
                    if '.' in value:
                        param_values.append(float(value.strip()))
                    else:
                        param_values.append(int(value.strip()))
                except ValueError:
                    param_values.append(value.strip())
        
        # 构建指标配置
        indicator_params = {}
        for i, (name, value) in enumerate(zip(param_names, param_values)):
            if i < len(param_values):
                indicator_params[name] = value
        
        # 创建指标配置字典
        indicator_config = {input.indicator_name: indicator_params}
        
        # 创建面板列表
        print(f"创建自定义布局: 股票={stock_list}, 周期={input.period}, 指标={indicator_config}")
        
        panel_info = []
        try:
            # 尝试创建UIPanel对象
            panels = []
            for stock in stock_list:
                try:
                    panel = UIPanel(stock, input.period, figures=[indicator_config])
                    panels.append(panel)
                    panel_info.append({
                        "stock": stock,
                        "period": input.period,
                        "figures": str(indicator_config),
                        "panel_type": str(type(panel)),
                        "panel_str": str(panel)
                    })
                except Exception as e:
                    error_msg = f"创建UIPanel对象失败: {str(e)}"
                    print(error_msg)
                    traceback.print_exc()
                    # 如果创建UIPanel对象失败，使用字典代替
                    panel_dict = {
                        "stock": stock,
                        "period": input.period,
                        "figures": [indicator_config]
                    }
                    panels.append(panel_dict)
                    panel_info.append({
                        "stock": stock,
                        "period": input.period,
                        "figures": str(indicator_config),
                        "panel_type": "dict",
                        "error": str(e)
                    })
            
            # 应用面板控制
            print(f"调用xtdata.apply_ui_panel_control(panels)")
            
            method_results = {}
            # 检查apply_ui_panel_control方法是否存在
            if hasattr(xtdata, 'apply_ui_panel_control'):
                try:
                    start_time = time.time()
                    result = xtdata.apply_ui_panel_control(panels)
                    end_time = time.time()
                    method_results["apply_ui_panel_control"] = {
                        "result": str(result),
                        "time_taken": end_time - start_time
                    }
                    print(f"apply_ui_panel_control结果: {result}, 耗时: {end_time - start_time}秒")
                except Exception as e:
                    error_msg = f"调用apply_ui_panel_control出错: {str(e)}"
                    print(error_msg)
                    traceback.print_exc()
                    method_results["apply_ui_panel_control"] = {"error": str(e)}
            else:
                print("警告: xtdata模块没有apply_ui_panel_control方法")
                method_results["apply_ui_panel_control"] = {"exists": False}
                
                # 尝试其他可能的方法名
                possible_methods = ['apply_panel_control', 'create_panel', 'show_panel', 'display_panel']
                for method_name in possible_methods:
                    if hasattr(xtdata, method_name):
                        print(f"尝试使用替代方法: {method_name}")
                        try:
                            method = getattr(xtdata, method_name)
                            start_time = time.time()
                            result = method(panels)
                            end_time = time.time()
                            method_results[method_name] = {
                                "result": str(result),
                                "time_taken": end_time - start_time
                            }
                            print(f"{method_name}结果: {result}, 耗时: {end_time - start_time}秒")
                            break
                        except Exception as e:
                            error_msg = f"调用{method_name}出错: {str(e)}"
                            print(error_msg)
                            traceback.print_exc()
                            method_results[method_name] = {"error": str(e)}
                else:
                    print("无法找到合适的方法来显示图表面板")
                    method_results["no_method_found"] = True
            
            # 尝试强制刷新UI
            try:
                if hasattr(xtdata, 'refresh_ui'):
                    print("尝试调用refresh_ui方法")
                    xtdata.refresh_ui()
                    method_results["refresh_ui"] = {"called": True}
            except Exception as e:
                print(f"调用refresh_ui出错: {str(e)}")
                method_results["refresh_ui"] = {"error": str(e)}
            
            # 等待一段时间，确保UI有时间更新
            time.sleep(0.5)
            
            # 返回结果
            return {
                "success": True,
                "message": f"已成功创建 {len(stock_list)} 个自定义布局面板",
                "details": {
                    "stocks": stock_list,
                    "period": input.period,
                    "indicator": input.indicator_name,
                    "parameter_names": param_names,
                    "parameter_values": param_values
                },
                "debug_info": {
                    "env_info": env_info,
                    "panel_info": panel_info,
                    "method_results": method_results
                }
            }
        except Exception as e:
            print(f"创建或应用面板时出错: {str(e)}")
            traceback.print_exc()
            return {"error": f"创建或应用面板时出错: {str(e)}"}
    except Exception as e:
        print(f"创建自定义布局出错: {str(e)}")
        traceback.print_exc()
        return {
            "error": str(e),
            "debug_info": {
                "traceback": traceback.format_exc()
            }
        }

async def main():
    """
    服务器的主入口点。

    此函数初始化并运行MCP服务器，处理传入的请求并将其分派给适当的处理程序。
    它还会在启动时打印所有已注册的工具。
    """
    # 打印所有注册的工具
    print("\n在server.py中打印所有工具:")
    tools = await handle_list_tools()
    for i, tool in enumerate(tools, 1):
        print(f"{i}. {tool.name} - {tool.description}")
    
    # Run the server using stdin/stdout streams
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="xtquantai",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())