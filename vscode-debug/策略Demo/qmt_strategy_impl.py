# -*- coding: utf-8 -*-

def on_init(ContextInfo, qmt):
    print("[INIT] External strategy loaded")
    data = get_etf_info("510300.SH")
    print("RESULT:", str(data)[:2000])


def on_bar(ContextInfo, qmt):
    barpos = ContextInfo.barpos
    timetag = ContextInfo.get_bar_timetag(barpos)
    bar_time = timetag_to_datetime(timetag, "%Y-%m-%d %H:%M:%S")

    stock = "%s.%s" % (ContextInfo.stockcode, ContextInfo.market)
    data = ContextInfo.get_market_data_ex(
        [],
        [stock],
        period="follow",
        end_time=timetag_to_datetime(timetag, "%Y%m%d%H%M%S"),
        count=1,
    )

    df = data[stock]
    if df.empty:
        print("[BAR]", barpos, bar_time, "no data")
        return

    row = df.iloc[-1]
    print("[BAR]", barpos, bar_time, stock, row.to_dict())


def on_after_init(ContextInfo, qmt):
    """初始化完成后执行"""
    print("[AFTER INIT] 初始化完成")


def on_backtest_finished(ContextInfo, qmt):
    """回测结束后自动执行"""
    print("========== 回测结束 ==========")
    print("最后处理的 barpos:", ContextInfo.barpos)


def on_stop(ContextInfo, qmt):
    """策略停止回调"""
    print("策略停止")