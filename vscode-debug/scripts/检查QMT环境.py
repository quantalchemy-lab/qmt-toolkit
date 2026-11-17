#coding:gbk
# 在 QMT 策略编辑器中新建策略，粘贴本文件内容并运行，检查调试环境
import sys


def init(ContextInfo):
    print('[VERSION]', sys.version)
    print('[64BIT]', sys.maxsize > 2 ** 32)
    print('[EXECUTABLE]', sys.executable)
    try:
        import debugpy
        print('[DEBUGPY] OK', debugpy.__version__, debugpy.__file__)
    except Exception as e:
        print('[DEBUGPY] FAIL', repr(e))


def handlebar(ContextInfo):
    pass