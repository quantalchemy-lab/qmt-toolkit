# encoding: gbk
# QMT Windows IPC 能力测试（Python 3.6）
# 单进程测试各接口可用性，不等同于真正的跨进程通信验证。
import os
import sys
import time
import tempfile

# 替换为对应的python虚拟环境路径
CONDA_ROOT = r"D:\xxxxxxxxxx\Anaconda3\envs\py36"
CONDA_DLLS = CONDA_ROOT + r"\DLLs"
CONDA_LIB = CONDA_ROOT + r"\Lib"
CONDA_PACKAGES = CONDA_LIB + r"\site-packages"
CONDA_SQLITE = CONDA_ROOT + r"\Library\bin\sqlite3.dll"


# 配置 Conda 模块搜索路径
def test_conda_paths():
    paths = [
        CONDA_DLLS,
        CONDA_LIB,
        CONDA_PACKAGES
    ]

    # 保留已有路径，避免重复
    for path in paths:
        if path in sys.path:
            sys.path.remove(path)

    # 优先搜索 Conda，保留原有 Python 路径作为后备
    sys.path[:0] = paths

    print("Python:", sys.version)

    for path in sys.path:
        print("PATH:", path)


# 不适用的测试单独标记为 SKIP，避免误判成接口封禁
class TestSkipped(Exception):
    pass


# 统一执行测试，单项失败不影响其他测试
def test(name, func):
    try:
        func()
        print("[PASS] " + name)
    except TestSkipped as e:
        print("[SKIP] %s: %s" % (name, e))
    except Exception as e:
        print("[FAIL] %s: %r" % (name, e))


# Windows API 辅助：声明参数类型，避免 64 位句柄截断
# 这些辅助函数仅供 Windows IPC 测试调用
def win_api(dll, name, result_type, arg_types):
    func = getattr(dll, name)
    func.restype = result_type
    func.argtypes = arg_types
    return func


def close_win_handles(*handles):
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    close = win_api(kernel, "CloseHandle", wintypes.BOOL, [wintypes.HANDLE])
    invalid = ctypes.c_void_p(-1).value
    for handle in handles:
        if handle not in (None, 0, invalid):
            close(handle)


# Python 信号：只测试注册处理器，不向 QMT 发送真正的系统信号
# Windows 的 Python signal 不等同于可任意发送的进程间消息
def test_signal():
    import signal
    import threading

    # QMT 可能在非 Python 主线程运行策略
    if threading.current_thread() is not threading.main_thread():
        raise TestSkipped("只能在 Python 主线程注册 signal")

    old_handler = signal.getsignal(signal.SIGBREAK)
    try:
        signal.signal(signal.SIGBREAK, lambda number, frame: None)
    finally:
        signal.signal(signal.SIGBREAK, old_handler)


# 具名 Event：打开同名事件，发送一次通知并验证自动复位
def test_event():
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = win_api(kernel, "CreateEventW", wintypes.HANDLE,
                     [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR])
    open_event = win_api(kernel, "OpenEventW", wintypes.HANDLE,
                         [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR])
    set_event = win_api(kernel, "SetEvent", wintypes.BOOL, [wintypes.HANDLE])
    wait = win_api(kernel, "WaitForSingleObject", wintypes.DWORD,
                   [wintypes.HANDLE, wintypes.DWORD])

    name = "Local\\QMT_EVENT_%d_%d" % (os.getpid(), int(time.time() * 1000000))
    receiver = sender = None
    try:
        receiver = create(None, False, False, name)
        if not receiver:
            raise ctypes.WinError(ctypes.get_last_error())

        # EVENT_MODIFY_STATE | SYNCHRONIZE
        sender = open_event(0x00100002, False, name)
        if not sender:
            raise ctypes.WinError(ctypes.get_last_error())

        assert wait(receiver, 0) == 258       # WAIT_TIMEOUT：尚无通知
        if not set_event(sender):
            raise ctypes.WinError(ctypes.get_last_error())
        assert wait(receiver, 0) == 0         # WAIT_OBJECT_0：收到通知
        assert wait(receiver, 0) == 258       # 自动复位后不再触发
    finally:
        close_win_handles(sender, receiver)


# 具名信号量：释放两次通知，接收端必须能消费两次
def test_semaphore():
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = win_api(kernel, "CreateSemaphoreW", wintypes.HANDLE,
                     [wintypes.LPVOID, wintypes.LONG, wintypes.LONG, wintypes.LPCWSTR])
    open_sem = win_api(kernel, "OpenSemaphoreW", wintypes.HANDLE,
                       [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR])
    release = win_api(kernel, "ReleaseSemaphore", wintypes.BOOL,
                      [wintypes.HANDLE, wintypes.LONG, wintypes.LPVOID])
    wait = win_api(kernel, "WaitForSingleObject", wintypes.DWORD,
                   [wintypes.HANDLE, wintypes.DWORD])

    name = "Local\\QMT_SEM_%d_%d" % (os.getpid(), int(time.time() * 1000000))
    receiver = sender = None
    try:
        receiver = create(None, 0, 3, name)  # 初始计数 0，最大计数 3
        if not receiver:
            raise ctypes.WinError(ctypes.get_last_error())

        # SEMAPHORE_MODIFY_STATE | SYNCHRONIZE
        sender = open_sem(0x00100002, False, name)
        if not sender:
            raise ctypes.WinError(ctypes.get_last_error())

        assert wait(receiver, 0) == 258
        if not release(sender, 2, None):
            raise ctypes.WinError(ctypes.get_last_error())
        assert wait(receiver, 0) == 0         # 消费第一次
        assert wait(receiver, 0) == 0         # 消费第二次
        assert wait(receiver, 0) == 258       # 计数归零
    finally:
        close_win_handles(sender, receiver)


# 匿名管道：验证单向字节流，通常适合父子进程
def test_pipe_anonymous():
    reader, writer = os.pipe()
    try:
        assert os.write(writer, b"PING") == 4
        assert os.read(reader, 4) == b"PING"
    finally:
        os.close(writer)
        os.close(reader)


# Windows 消息式通道：Mailslot，不等于持久化消息中间件
# Mailslot 读句柄属于 Overlapped IO，需提供 OVERLAPPED 结构
def test_message_queue():
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = win_api(kernel, "CreateMailslotW", wintypes.HANDLE,
                     [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID])
    open_file = win_api(kernel, "CreateFileW", wintypes.HANDLE,
                        [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                         wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE])
    write = win_api(kernel, "WriteFile", wintypes.BOOL,
                    [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                     ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID])
    read = win_api(kernel, "ReadFile", wintypes.BOOL,
                   [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                    ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID])
    get_result = win_api(kernel, "GetOverlappedResult", wintypes.BOOL,
                         [wintypes.HANDLE, wintypes.LPVOID,
                          ctypes.POINTER(wintypes.DWORD), wintypes.BOOL])
    create_event = win_api(kernel, "CreateEventW", wintypes.HANDLE,
                           [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR])
    reset_event = win_api(kernel, "ResetEvent", wintypes.BOOL,
                          [wintypes.HANDLE])

    class Overlapped(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_size_t),
            ("InternalHigh", ctypes.c_size_t),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE)
        ]

    name = r"\\.\mailslot\QMT_MSG_%d_%d" % (
        os.getpid(), int(time.time() * 1000000)
    )
    invalid = ctypes.c_void_p(-1).value
    server = client = event = None

    try:
        server = create(name, 0, 1000, None)
        if server in (None, invalid):
            raise ctypes.WinError(ctypes.get_last_error())

        # GENERIC_WRITE / FILE_SHARE_READ / OPEN_EXISTING
        client = open_file(name, 0x40000000, 1, None, 3, 0x80, None)
        if client in (None, invalid):
            raise ctypes.WinError(ctypes.get_last_error())

        event = create_event(None, True, False, None)
        if not event:
            raise ctypes.WinError(ctypes.get_last_error())

        # 先发送两条消息，再逐条读取，检查消息边界和顺序
        for message in (b"ONE", b"TWO22"):
            sent = wintypes.DWORD(0)
            buf = ctypes.create_string_buffer(message)
            if not write(client, buf, len(message), ctypes.byref(sent), None):
                raise ctypes.WinError(ctypes.get_last_error())
            assert sent.value == len(message)

        for expected in (b"ONE", b"TWO22"):
            if not reset_event(event):
                raise ctypes.WinError(ctypes.get_last_error())
            buf = ctypes.create_string_buffer(64)
            received = wintypes.DWORD(0)
            overlapped = Overlapped()
            overlapped.hEvent = event

            done = read(server, buf, 64, ctypes.byref(received), ctypes.byref(overlapped))
            if not done:
                error = ctypes.get_last_error()
                if error != 997:  # ERROR_IO_PENDING
                    raise ctypes.WinError(error)
                if not get_result(server, ctypes.byref(overlapped),
                                  ctypes.byref(received), True):
                    raise ctypes.WinError(ctypes.get_last_error())

            assert buf.raw[:received.value] == expected
    finally:
        close_win_handles(event, client, server)


# 1. 文件读写
def test_file():
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "test.txt")
        with open(path, "wb") as f:
            f.write(b"hello")
        with open(path, "rb") as f:
            assert f.read() == b"hello"


# 2. Socket 本地通信
def test_socket():
    import socket

    with socket.socket() as server, socket.socket() as client:
        server.settimeout(2)
        client.settimeout(2)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        client.connect(server.getsockname())

        conn, _ = server.accept()
        with conn:
            conn.settimeout(2)
            client.sendall(b"hello")
            assert conn.recv(5) == b"hello"


# 3. 测试启动外部进程
def test_subprocess():
    import subprocess

    p = subprocess.run(
        ["cmd.exe", "/c", "exit", "0"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=3
    )
    assert p.returncode == 0, p.stderr


# 4. 测试外部进程输出捕获
def test_subprocess_pipe():
    import subprocess

    p = subprocess.run(
        ["cmd.exe", "/c", "echo", "hello"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=3
    )
    assert p.returncode == 0, p.stderr
    assert b"hello" in p.stdout


# 5. ctypes 调用 Windows API
def test_ctypes():
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetCurrentProcessId.restype = ctypes.c_ulong
    assert kernel32.GetCurrentProcessId() > 0


# 6. WinAPI 具名管道双向通信
def test_pipe():
    import _winapi

    name = r"\\.\pipe\QMT_TEST_%d_%d" % (os.getpid(), int(time.time() * 1000))

    # 安全属性传 0；同步读写模式传 False
    server = _winapi.CreateNamedPipe(name, 3, 0, 1, 1024, 1024, 0, 0)
    try:
        client = _winapi.CreateFile(name, 0xC0000000, 0, 0, 3, 0, 0)
        try:
            try:
                _winapi.ConnectNamedPipe(server, False)
            except OSError as e:
                # 535：客户端已连接，不是失败
                if getattr(e, "winerror", None) != 535:
                    raise

            # 客户端发送，服务端接收
            count, err = _winapi.WriteFile(client, b"PING", False)
            assert count == 4 and err == 0
            data, err = _winapi.ReadFile(server, 4, False)
            assert data == b"PING" and err == 0

            # 服务端发送，客户端接收
            count, err = _winapi.WriteFile(server, b"PONG", False)
            assert count == 4 and err == 0
            data, err = _winapi.ReadFile(client, 4, False)
            assert data == b"PONG" and err == 0
        finally:
            _winapi.CloseHandle(client)
    finally:
        _winapi.CloseHandle(server)


# 7. SQLite 数据库读写     
# 保留 DLL 对象引用
conda_sqlite_dll = None
# 测试优先加载 Conda SQLite
def test_conda_sqlite():
    import os
    import ctypes
    global conda_sqlite_dll

    kernel32 = ctypes.WinDLL("kernel32")

    # 获取已经加载的同名 DLL
    kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    kernel32.GetModuleHandleW.restype = ctypes.c_void_p

    kernel32.GetModuleFileNameW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_uint
    ]
    kernel32.GetModuleFileNameW.restype = ctypes.c_uint

    def get_dll_path(handle):
        buf = ctypes.create_unicode_buffer(32768)
        size = kernel32.GetModuleFileNameW(
            handle, buf, len(buf)
        )
        if not size or size >= len(buf):
            raise RuntimeError("无法获取 DLL 路径")
        return buf.value

    # 如果已有同名 DLL，先检查来源
    handle = kernel32.GetModuleHandleW("sqlite3.dll")

    if handle:
        loaded_path = get_dll_path(handle)
        print("已加载:", loaded_path)

        if os.path.normcase(loaded_path) != os.path.normcase(CONDA_SQLITE):
            raise RuntimeError("已存在其他版本 sqlite3.dll")

    else:
        # 使用完整路径加载 Conda 的 SQLite
        conda_sqlite_dll = ctypes.WinDLL(CONDA_SQLITE)
        loaded_path = get_dll_path(conda_sqlite_dll._handle)

        print("实际加载:", loaded_path)

        assert os.path.normcase(loaded_path) == os.path.normcase(
            CONDA_SQLITE
        ), "DLL 来源不符合预期"

    # 验证 SQLite 标准 API
    dll = conda_sqlite_dll or ctypes.WinDLL(CONDA_SQLITE)
    dll.sqlite3_libversion.restype = ctypes.c_char_p
    print("DLL SQLite:", dll.sqlite3_libversion().decode())

    # 测试 Python SQLite 扩展是否可用
    import sqlite3
    print("Python SQLite:", sqlite3.sqlite_version)

    conn = sqlite3.connect(":memory:")
    try:
        row = conn.execute("SELECT 123").fetchone()
        assert row == (123,)
    finally:
        conn.close()


sqlite_dll = None

def init_sqlite():
    import ctypes
    global sqlite_dll

    # 预加载指定版本的 DLL
    sqlite_dll = ctypes.CDLL(CONDA_ROOT + r"\Library\bin\sqlite3.dll")

    # 导入 Python 模块并测试
    import sqlite3
    print("SQLite:", sqlite3.sqlite_version)
    return sqlite3


def test_sqlite():
    sqlite3 = init_sqlite()

    conn = sqlite3.connect(":memory:")
    try:
        assert conn.execute("SELECT 1").fetchone() == (1,)
    finally:
        conn.close()

# SQLite 内存数据库完整测试
def test_sqlite_crud():
    import sqlite3

    conn = sqlite3.connect(":memory:")

    try:
        # 创建表
        conn.execute("""
            CREATE TABLE signals (
                id INTEGER PRIMARY KEY,
                symbol TEXT,
                side TEXT,
                ratio REAL
            )
        """)

        # 插入交易信号
        conn.execute(
            "INSERT INTO signals VALUES (?, ?, ?, ?)",
            (1, "600000.SH", "BUY", 0.2)
        )
        conn.commit()

        # 查询
        row = conn.execute(
            "SELECT symbol, side, ratio FROM signals"
        ).fetchone()

        assert row == ("600000.SH", "BUY", 0.2)

        # 更新
        conn.execute(
            "UPDATE signals SET ratio = 0.5 WHERE id = 1"
        )
        conn.commit()

        ratio = conn.execute(
            "SELECT ratio FROM signals WHERE id = 1"
        ).fetchone()[0]

        assert ratio == 0.5

        # 删除
        conn.execute("DELETE FROM signals WHERE id = 1")
        conn.commit()

        count = conn.execute(
            "SELECT COUNT(*) FROM signals"
        ).fetchone()[0]

        assert count == 0

    finally:
        conn.close()


# 8. 环境变量读写
def test_environ():
    key = "QMT_TEST"
    old_value = os.environ.get(key)
    try:
        os.environ[key] = "hello"
        assert os.environ[key] == "hello"
    finally:
        if old_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old_value


# 9. 多线程
def test_threading():
    import threading

    done = threading.Event()
    thread = threading.Thread(target=done.set)
    thread.daemon = True
    thread.start()
    thread.join(2)
    assert done.is_set() and not thread.is_alive()


# 10. 匿名共享内存
def test_mmap_anonymous():
    import mmap

    with mmap.mmap(-1, 1024) as mem:
        mem.write(b"HELLO")
        mem.seek(0)
        assert mem.read(5) == b"HELLO"


# 11. 具名共享内存（同进程双映射）
def test_mmap_named():
    import mmap

    name = "QMT_MMAP_%d_%d" % (os.getpid(), int(time.time() * 1000))
    with mmap.mmap(-1, 1024, tagname=name) as writer:
        with mmap.mmap(-1, 1024, tagname=name) as reader:
            writer[:4] = b"PING"
            assert reader[:4] == b"PING"
            reader[:4] = b"PONG"
            assert writer[:4] == b"PONG"


# 12. 注册表通信（同进程模拟写入、读取及确认）
def test_registry():
    import winreg
    import json

    path = r"Software\QMT_IPC_TEST_%d_%d" % (os.getpid(), int(time.time() * 1000))
    signal = {"symbol": "600000.SH", "side": "BUY", "ratio": 0.2}

    try:
        # 写入模拟交易信号
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
            winreg.SetValueEx(key, "signal", 0, winreg.REG_SZ, json.dumps(signal))

        # 重新打开注册表，读取信号并写入 ACK
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0,
                            winreg.KEY_READ | winreg.KEY_WRITE) as key:
            data, value_type = winreg.QueryValueEx(key, "signal")
            assert value_type == winreg.REG_SZ
            assert json.loads(data) == signal
            winreg.SetValueEx(key, "ack", 0, winreg.REG_SZ, "RECEIVED")

        # 验证确认消息
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            ack, _ = winreg.QueryValueEx(key, "ack")
            assert ack == "RECEIVED"
    finally:
        # 仅删除本次测试创建的注册表项
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except FileNotFoundError:
            pass


# 13. # _winapi 文件读写测试
# 测试 _winapi 文件读写
def test_winapi_file():
    import _winapi

    # 使用已有且获授权的测试目录
    folder = os.environ.get("USERPROFILE")
    if not folder:
        raise RuntimeError("未找到 USERPROFILE")

    path = os.path.join(
        folder, "qmt_winapi_%d.bin" % os.getpid()
    )
    content = b"QMT_WINAPI_FILE_OK"
    created = False

    try:
        # 创建文件并写入
        handle = _winapi.CreateFile(
            path, 0xC0000000, 0, 0, 2, 0x80, 0
        )
        created = True

        try:
            count, err = _winapi.WriteFile(
                handle, content, False
            )
            assert count == len(content) and err == 0
        finally:
            _winapi.CloseHandle(handle)

        # 重新打开文件并读取
        handle = _winapi.CreateFile(
            path, 0x80000000, 0, 0, 3, 0x80, 0
        )

        try:
            data, err = _winapi.ReadFile(
                handle, len(content), False
            )
            assert err == 0 and data == content
        finally:
            _winapi.CloseHandle(handle)

    finally:
        # 清理失败不影响读写测试结果
        if created:
            try:
                os.remove(path)
            except Exception as e:
                print("[WARN] 清理失败:", repr(e))
                print("[WARN] 遗留文件:", path)

        
# QMT 测试入口
def main():
    print("=" * 45)
    print("QMT Sandbox Test")
    print("Python:", sys.version)
    print("PID:", os.getpid())
    print("=" * 45)

    test("Conda Paths", test_conda_paths)
    test("Conda SQLite Preload", test_conda_sqlite)
    test("SQLite CRUD", test_sqlite_crud)
    
    test("File IO", test_file)
    # 六大 IPC 通信机制（信号、信号量、管道、消息队列、共享内存、Socket）
    test("Signal Handler", test_signal)
    test("Named Event", test_event)
    test("Semaphore", test_semaphore)
    test("Anonymous Pipe", test_pipe_anonymous)
    test("Message Queue (Mailslot)", test_message_queue)
    test("Socket", test_socket)
    test("Subprocess", test_subprocess)
    test("Subprocess Pipe", test_subprocess_pipe)
    test("ctypes", test_ctypes)
    test("WinAPI Pipe", test_pipe)
    test("SQLite", test_sqlite)
    test("Environment", test_environ)
    test("Threading", test_threading)
    test("mmap Anonymous", test_mmap_anonymous)
    test("mmap Named", test_mmap_named)
    test("Registry", test_registry)
    test("WinAPI File IO", test_winapi_file)

    print("=" * 45)
    print("Test Finished")


main()