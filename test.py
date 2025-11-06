"""
用于手动测试xtquantai功能的脚本。

此脚本包含一些示例代码片段，用于测试`xtquant`库的各种功能，
例如获取股票详情和创建图表面板。
"""
from xtquant import xtdata
from xtquant.xtdata import UIPanel


# 输出平安银行的相关信息 
# data = xtdata.get_instrument_detail("000001.SZ")  
# print(data)


stock_list = ['000001.SZ', '600519.SH']
# 针对自选板块中的品种，设置指标，对应参数
panels = [UIPanel(stock, '1d', figures=[{'ma':{'n1':5}}]) for stock in stock_list]
xtdata.apply_ui_panel_control(panels)
