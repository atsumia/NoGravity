#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
NoGravity • Universal Doctor & Environment Patcher for Google Antigravity
================================================================================
Local patcher and diagnostics suite for Google Antigravity.
Reports server location errors separately from the local binary patch.
A binary patch cannot change the service's server-side location decision.
================================================================================
"""

import os
import sys
import time
import shutil
import subprocess
import winreg
import urllib.request
import urllib.error
import json
import hashlib
import re
import argparse
from pathlib import Path

# Force UTF-8 encoding on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# --- ANSI Color Palette ---
ESC = "\033["
RESET = f"{ESC}0m"
BOLD = f"{ESC}1m"
DIM = f"{ESC}2m"
RED = f"{ESC}91m"
GREEN = f"{ESC}92m"
YELLOW = f"{ESC}93m"
BLUE = f"{ESC}94m"
MAGENTA = f"{ESC}95m"
CYAN = f"{ESC}96m"
WHITE = f"{ESC}97m"

# --- Target Paths ---
DEFAULT_LS_PATH = Path(os.path.expandvars(r"%LOCALAPPDATA%\Programs\antigravity\resources\bin\language_server.exe"))
ELEVATE_EXE = Path(os.path.expandvars(r"%LOCALAPPDATA%\Programs\antigravity\resources\elevate.exe"))


def get_ls_path() -> Path:
    """Locate language_server.exe in standard or custom paths."""
    custom = os.environ.get("NOGRAVITY_LS_PATH")
    if custom:
        return Path(custom)
    if DEFAULT_LS_PATH.exists():
        return DEFAULT_LS_PATH
    # Search common alternative locations
    alternatives = [
        Path(os.path.expandvars(r"%PROGRAMFILES%\Antigravity\resources\bin\language_server.exe")),
        Path(os.path.expandvars(r"%PROGRAMFILES(X86)%\Antigravity\resources\bin\language_server.exe")),
        Path(os.path.expandvars(r"%USERPROFILE%\AppData\Local\Programs\antigravity\resources\bin\language_server.exe")),
    ]
    for alt in alternatives:
        if alt.exists():
            return alt
    return DEFAULT_LS_PATH


def get_cli_path() -> Path:
    custom = os.environ.get("NOGRAVITY_CLI_PATH")
    if custom:
        return Path(custom)
    default = Path(os.path.expandvars(r"%LOCALAPPDATA%\agy\bin\agy.exe"))
    if default.exists():
        return default
    found = shutil.which("agy.exe")
    return Path(found) if found else default


def get_targets(target="all"):
    paths = {"desktop": get_ls_path(), "cli": get_cli_path()}
    if target != "all":
        return [(target, paths[target])]
    return [(name, path) for name, path in paths.items() if path.exists()]


def apply_targets(target="all", silent=False):
    targets = get_targets(target)
    if not targets:
        if not silent:
            print("Antigravity Desktop и CLI не найдены. Задайте NOGRAVITY_LS_PATH или NOGRAVITY_CLI_PATH.")
        return False
    success = True
    for name, path in targets:
        if not silent:
            print(f"\n[{name}] {path}")
        if not apply_nogravity_patch(silent=silent, path=path):
            success = False
    return success


def is_admin() -> bool:
    """Check if current process has administrative privileges."""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def run_elevated(cmd_list):
    """Run command elevated if possible."""
    if is_admin():
        return subprocess.run(cmd_list, capture_output=True, text=True)
    if ELEVATE_EXE.exists():
        return subprocess.run([str(ELEVATE_EXE)] + cmd_list, capture_output=True, text=True)
    ps_args = subprocess.list2cmdline(cmd_list[1:]).replace("'", "''")
    ps_exe = cmd_list[0].replace("'", "''")
    ps_cmd = f"Start-Process -FilePath '{ps_exe}' -ArgumentList '{ps_args}' -Verb RunAs -WindowStyle Hidden -Wait"
    return subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd], capture_output=True, text=True)


def get_egress_info() -> str:
    """Fetch current public IP and location info."""
    try:
        req = urllib.request.Request("https://ipinfo.io/json", headers={"User-Agent": "curl/7.88.1"})
        with urllib.request.urlopen(req, timeout=4) as res:
            data = json.loads(res.read().decode("utf-8"))
            ip = data.get("ip", "Unknown")
            country = data.get("country", "")
            city = data.get("city", "")
            org = data.get("org", "")
            return f"{ip} ({city}, {country}) [{org[:24]}]"
    except Exception:
        return "Не удалось определить (офлайн или блокировка внешних запросов)"


def recent_location_error(log_path=None):
    """Return only location evidence from the log, never tokens or raw log lines."""
    path = Path(log_path) if log_path else Path(os.path.expandvars(r"%APPDATA%\Antigravity\logs\language_server.log"))
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - 512 * 1024))
            lines = handle.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if "LOCATION_NOT_ELIGIBLE" not in line:
            continue
        location = re.search(r"Detected location:\s*([A-Z]{2})", line)
        timestamp = re.search(r"\b[WIE](\d{4}\s+\d{2}:\d{2}:\d{2})", line)
        return {"reason": "LOCATION_NOT_ELIGIBLE", "detected_location": location.group(1) if location else None,
                "log_time": timestamp.group(1) if timestamp else None}
    return None


def http_verdict(status, body=""):
    if any(marker in body.lower() for marker in ["location_not_eligible", "user location is not supported", "your location is not eligible"]):
        return "Серверный геоблок"
    return "Ответ HTTP; доступ аккаунта не проверен"


def inspect_system(target="all"):
    ls = get_ls_path()
    bak = ls.with_suffix(".exe.bak_original")

    info = {
        "ls_path": str(ls),
        "binary_exists": ls.exists(),
        "has_backup": bak.exists(),
        "inexigible_count": 0,
        "ineligible_count": 0,
        "ag_ls_proxy_count": 0,
        "https_proxy_count": 0,
        "env_ag_ls_proxy": None,
        "env_ag_ls_proxy_machine": None,
        "inspection_errors": [],
        "nrpt_hijacked": False,
        "conflicting_tasks": False,
        "conflicting_process_running": False,
        "watchdog_active": False,
        "server_location_error": recent_location_error(),
        "targets": [],
    }

    if info["binary_exists"]:
        try:
            data = ls.read_bytes()
            info["inexigible_count"] = data.count(b"inexigible")
            info["ineligible_count"] = data.count(b"ineligible")
            info["ag_ls_proxy_count"] = data.count(b"AG_LS_PROXY")
            info["https_proxy_count"] = data.count(b"https_proxy")
        except OSError:
            info["inspection_errors"].append("binary")

    for name, path in get_targets(target):
        entry = {"name": name, "path": str(path), "exists": path.exists(),
                 "has_backup": path.with_suffix(".exe.bak_original").exists(),
                 "ineligible_count": 0, "inexigible_count": 0, "ag_ls_proxy_count": 0}
        try:
            binary = path.read_bytes()
            for marker, key in [(b"ineligible", "ineligible_count"), (b"inexigible", "inexigible_count"), (b"AG_LS_PROXY", "ag_ls_proxy_count")]:
                entry[key] = binary.count(marker)
        except OSError:
            info["inspection_errors"].append(name + "_binary")
        info["targets"].append(entry)

    # Check environment variable
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ) as key:
            info["env_ag_ls_proxy"] = bool(winreg.QueryValueEx(key, "AG_LS_PROXY")[0])
    except FileNotFoundError:
        pass
    except Exception:
        info["inspection_errors"].append("user_environment")

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment", 0, winreg.KEY_READ) as key:
            info["env_ag_ls_proxy_machine"] = bool(winreg.QueryValueEx(key, "AG_LS_PROXY")[0])
    except FileNotFoundError:
        pass
    except OSError:
        info["inspection_errors"].append("machine_environment")

    # Check NRPT DNS hijacks (e.g. 127.0.0.53 rule)
    try:
        res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", "$ErrorActionPreference = 'Stop'; Get-DnsClientNrptRule | Where-Object { ($_.NameServers -contains '127.0.0.53') -and ($_.Namespace -like '*googleapis.com*') } | Select-Object -ExpandProperty Namespace"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode != 0:
            info["inspection_errors"].append("nrpt")
        if any("cloudcode-pa.googleapis.com" in l for l in res.stdout.splitlines()):
            info["nrpt_hijacked"] = True
    except Exception:
        info["inspection_errors"].append("nrpt")

    # Check scheduled tasks & watchdog
    try:
        res_tasks = subprocess.run(["schtasks", "/query", "/fo", "CSV"], capture_output=True, text=True, timeout=10)
        if res_tasks.returncode != 0:
            info["inspection_errors"].append("scheduled_tasks")
        if any(marker in res_tasks.stdout for marker in ["ag_dns", "AG Unlocker", "NoVPN Antigravity Watchdog"]):
            info["conflicting_tasks"] = True
        if "NoGravity Watchdog" in res_tasks.stdout or "NoVPN Antigravity Watchdog" in res_tasks.stdout:
            info["watchdog_active"] = True
    except Exception:
        info["inspection_errors"].append("scheduled_tasks")

    # Check conflicting processes (e.g. ag_dns.exe)
    try:
        res_proc = subprocess.run(["tasklist", "/fi", "imagename eq ag_dns.exe"], capture_output=True, text=True, timeout=10)
        if res_proc.returncode != 0:
            info["inspection_errors"].append("processes")
        if "ag_dns.exe" in res_proc.stdout:
            info["conflicting_process_running"] = True
    except Exception:
        info["inspection_errors"].append("processes")

    return info


def print_banner(info):
    os.system("cls" if os.name == "nt" else "clear")
    print(f"""{CYAN}{BOLD}
  ███╗   ██╗ ██████╗  ██████╗ ██████╗  █████╗ ██╗   ██╗██╗████████╗██╗   ██╗
  ████╗  ██║██╔═══██╗██╔════╝ ██╔══██╗██╔══██╗██║   ██║██║╚══██╔══╝╚██╗ ██╔╝
  ██╔██╗ ██║██║   ██║██║  ███╗██████╔╝███████║██║   ██║██║   ██║    ╚████╔╝ 
  ██║╚██╗██║██║   ██║██║   ██║██╔══██╗██╔══██║╚██╗ ██╔╝██║   ██║     ╚██╔╝  
  ██║ ╚████║╚██████╔╝╚██████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║   ██║      ██║   
  ╚═╝  ╚═══╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝   ╚═╝      ╚═╝   
        {WHITE}Antigravity Desktop & CLI Doctor v2.1.0{CYAN}
  {DIM}======================================================================={RESET}""")

    print(f"{BOLD}{WHITE}  [ СИСТЕМНЫЙ ДАШБОРД СОВМЕСТИМОСТИ ]{RESET}")

    # 1. Binary location
    if not info["binary_exists"]:
        bin_str = f"{RED}[ НЕ НАЙДЕН ] {info['ls_path']}{RESET}"
    else:
        bin_str = f"{GREEN}[ НАЙДЕН ] {info['ls_path']}{RESET}"
    print(f"  ● Языковой сервер     : {bin_str}")
    for entry in info["targets"]:
        state = "локальный патч" if entry["inexigible_count"] else "без патча"
        if not entry["exists"]:
            state = "не найден"
        print(f"  ● {entry['name']:<18}: {state} — {entry['path']}")

    # 2. Regional Protobuf Gating
    if info["inexigible_count"] > 0:
        reg_str = f"{YELLOW}[ ЛОКАЛЬНЫЙ ПАТЧ ] {info['inexigible_count']} строк inexigible; доступ сервера не подтверждён{RESET}"
    elif info["ineligible_count"] > 0:
        reg_str = f"{WHITE}[ БЕЗ ЛОКАЛЬНОГО ПАТЧА ] {info['ineligible_count']} строк ineligible{RESET}"
    else:
        reg_str = f"{YELLOW}[ НЕИЗВЕСТНО ] Сигнатуры Protobuf не найдены{RESET}"
    print(f"  ● Локальный патч      : {reg_str}")
    if info["server_location_error"]:
        evidence = info["server_location_error"]
        print(f"  ● Последний геоблок   : {RED}Google: {evidence['reason']}, регион {evidence['detected_location']}, лог {evidence['log_time']}{RESET}")

    # 3. Proxy routing hook
    if info["ag_ls_proxy_count"] > 0:
        hook_str = f"{YELLOW}[ СТОРОННЯЯ СТРОКА ] AG_LS_PROXY обнаружен в бинарнике{RESET}"
    else:
        hook_str = f"{WHITE}[ НЕ НАЙДЕН ] AG_LS_PROXY отсутствует; маршрут VPN проверяется отдельно{RESET}"
    print(f"  ● Сетевой перехват    : {hook_str}")

    # 4. Conflicting background services
    if info["conflicting_process_running"] or info["conflicting_tasks"]:
        conf_str = f"{YELLOW}[ АКТИВНЫ ] (Процесс ag_dns: {'Да' if info['conflicting_process_running'] else 'Нет'}, Задачи: {'Да' if info['conflicting_tasks'] else 'Нет'}){RESET}"
    else:
        conf_str = f"{GREEN}[ ЧИСТО ] Конфликтующие локальные демоны отсутствуют{RESET}"
    print(f"  ● Сторонние хуки      : {conf_str}")

    # 5. NRPT DNS Hijack
    if info["nrpt_hijacked"]:
        nrpt_str = f"{YELLOW}[ ПЕРЕХВАТ 127.0.0.53 ] DNS запросы CloudCode направляются на локальный резолвер{RESET}"
    else:
        nrpt_str = f"{WHITE}[ НЕ НАЙДЕН ] Правило CloudCode → 127.0.0.53 не обнаружено{RESET}"
    print(f"  ● DNS маршрутизация   : {nrpt_str}")

    # 6. Autonomous Watchdog
    if info["watchdog_active"]:
        wd_str = f"{WHITE}[ ЗАРЕГИСТРИРОВАНА ] Патч проверяется при входе в Windows{RESET}"
    else:
        wd_str = f"{DIM}[ ОТКЛЮЧЕНА ] Фоновая авто-служба не установлена{RESET}"
    print(f"  ● Авто-служба Watchdog: {wd_str}")
    if info["inspection_errors"]:
        print(f"  {YELLOW}Не удалось проверить: {', '.join(info['inspection_errors'])}. Статус этих проверок неизвестен.{RESET}")

    print(f"{CYAN}{DIM}  -----------------------------------------------------------------------{RESET}")


def patched_bytes(data: bytes) -> bytes:
    """Apply only the equal-length local flag patch; never resize an executable."""
    if not data.startswith(b"MZ"):
        raise ValueError("Файл не является Windows executable.")
    if b"AG_LS_PROXY" in data:
        raise ValueError("Обнаружен сторонний AG_LS_PROXY. Восстановите оригинал этой версии Antigravity; замена на https_proxy повреждает exe.")
    if b"ineligible" not in data and b"inexigible" not in data:
        raise ValueError("Сигнатура патча не найдена: эта версия не поддерживается.")
    result = data.replace(b"ineligible", b"inexigible")
    if len(result) != len(data):
        raise ValueError("Изменился размер executable; запись запрещена.")
    return result


def apply_nogravity_patch(silent: bool = False, path=None) -> bool:
    """Patch a closed application, preserving the original for each version."""
    ls = Path(path) if path is not None else get_ls_path()
    bak = ls.with_suffix(".exe.bak_original")
    tmp_path = ls.with_suffix(".exe.tmp")
    try:
        data = ls.read_bytes()
        result = patched_bytes(data)
        if result == data:
            if not silent:
                print(f"{YELLOW}[=] Локальный патч уже присутствует. Доступ сервера проверяется отдельно через --diag.{RESET}")
            return True
        processes = subprocess.run(["tasklist", "/fo", "CSV", "/nh"], capture_output=True, text=True, timeout=10)
        if processes.returncode != 0:
            raise RuntimeError("Не удалось проверить запущенные процессы; запись отменена.")
        names = {line.split(',')[0].strip('"').lower() for line in processes.stdout.splitlines()}
        blocked = {ls.name.lower()}
        if ls.name.lower() == "language_server.exe":
            blocked.add("antigravity.exe")
        if names & blocked:
            raise RuntimeError(f"Закройте {ls.name} перед применением патча.")
        if bak.exists() and bak.read_bytes() != data:
            old = bak.read_bytes()
            archive = ls.with_name(ls.name + "." + hashlib.sha256(old).hexdigest() + ".bak_original")
            if not archive.exists():
                shutil.copy2(bak, archive)
        shutil.copy2(ls, bak)
        tmp_path.write_bytes(result)
        os.replace(tmp_path, ls)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as e:
        if not silent:
            print(f"{RED}[-] Патч не применён: {e}{RESET}")
        if tmp_path.exists():
            tmp_path.unlink()
        return False
    if not silent:
        print(f"{GREEN}[ГОТОВО] Локальный патч применён, размер exe сохранён. Серверный LOCATION_NOT_ELIGIBLE этим не снимается.{RESET}")
    return True


def clean_conflicts():
    """Remove background DNS hijackers, conflicting scheduled tasks, and NRPT rules."""
    print(f"\n{BOLD}{CYAN}[*] Очистка конфликтующих хуков и сторонних служб...{RESET}")
    if not is_admin():
        print(f"{RED}[-] Для очистки системных правил запустите 3_Clean_Conflicts.bat от администратора.{RESET}")
        return False

    # 1. Stop background processes
    subprocess.run(["taskkill", "/F", "/IM", "ag_dns.exe"], capture_output=True)
    subprocess.run(["taskkill", "/F", "/IM", "AG_2.28.2.exe"], capture_output=True)
    print(f"  {GREEN}[+] Фоновые процессы сторонних демонов остановлены{RESET}")

    # 2. Remove scheduled tasks
    ps_tasks = """
    $tasks = @('AG Unlocker Watchdog', 'AG Unlocker DNS', 'NoVPN Antigravity Watchdog');
    foreach ($t in $tasks) {
        Stop-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $t -Confirm:$false -ErrorAction SilentlyContinue
    }
    """
    subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_tasks], capture_output=True)
    run_elevated(["schtasks.exe", "/delete", "/tn", "AG Unlocker DNS", "/f"])
    run_elevated(["schtasks.exe", "/delete", "/tn", "AG Unlocker Watchdog", "/f"])
    print(f"  {GREEN}[+] Конфликтующие задачи автозапуска удалены из планировщика{RESET}")

    # 3. Clean environment variables
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, "AG_LS_PROXY")
            print(f"  {GREEN}[+] Переменная AG_LS_PROXY удалена из реестра HKCU{RESET}")
    except FileNotFoundError:
        pass

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment", 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, "AG_LS_PROXY")
            print(f"  {GREEN}[+] Переменная AG_LS_PROXY удалена из реестра HKLM{RESET}")
    except Exception:
        pass

    os.environ.pop("AG_LS_PROXY", None)

    # 4. Remove NRPT DNS hijack rules
    ps_nrpt = """
    Get-DnsClientNrptRule | Where-Object { 
        ($_.Namespace -like '*googleapis.com*') -and
        ($_.NameServers -contains '127.0.0.53')
    } | Remove-DnsClientNrptRule -Force
    """
    run_elevated(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_nrpt])
    print(f"  {GREEN}[+] Правила NRPT перехвата DNS (127.0.0.53) очищены{RESET}")

    remaining = inspect_system()
    if remaining["inspection_errors"] or remaining["nrpt_hijacked"] or remaining["conflicting_tasks"] or remaining["conflicting_process_running"] or remaining["env_ag_ls_proxy"] or remaining["env_ag_ls_proxy_machine"]:
        print(f"{RED}[-] Остались конфликтующие настройки. Очистка не завершена.{RESET}")
        return False
    print(f"\n{GREEN}{BOLD}[ГОТОВО] Проверка известных конфликтов завершена.{RESET}")
    return True


def remove_watchdog(silent: bool = False):
    """Delete and verify removal of the known watchdog tasks."""
    command = """
    $ErrorActionPreference = 'Stop';
    foreach ($name in @('NoGravity Watchdog', 'NoVPN Antigravity Watchdog')) {
        Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false;
        if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) { throw 'Watchdog task still exists' }
    }
    """
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=15)
    if not silent:
        if result.returncode == 0:
            print("Watchdog удалён; отсутствие задач проверено.")
        else:
            print("Не удалось удалить Watchdog. Повторите от администратора.")
    return result.returncode == 0


def restore_factory_original(path=None):
    """Restore virgin language_server.exe from original backup and remove autonomous watchdog."""
    ls = Path(path) if path is not None else get_ls_path()
    bak = ls.with_suffix(".exe.bak_original")

    print(f"\n{BOLD}{YELLOW}[*] Заводской откат Antigravity к оригиналу...{RESET}")
    if not bak.exists():
        print(f"{RED}[-] Оригинальный резервный бэкап {bak.name} не найден!{RESET}")
        return False

    try:
        original = bak.read_bytes()
        current = ls.read_bytes()
        if current != original and current != patched_bytes(original):
            print(f"{RED}[-] Бэкап не соответствует текущему бинарнику. Откат отменён; переустановите текущую версию Antigravity.{RESET}")
            return False
    except (OSError, ValueError) as e:
        print(f"{RED}[-] Не удалось проверить бэкап: {e}{RESET}")
        return False

    choice = input(f"{WHITE}Вернуть заводской бинарник и полностью удалить авто-службу Watchdog? (y/N): {RESET}").strip().lower()
    if choice != "y":
        return False

    # 1. Remove autonomous watchdog service so it will never re-apply the patch
    if not remove_watchdog():
        return False

    # 2. Stop running Antigravity processes
    subprocess.run(["taskkill", "/F", "/IM", ls.name], capture_output=True, timeout=10)
    if ls.name.lower() == "language_server.exe":
        subprocess.run(["taskkill", "/F", "/IM", "Antigravity.exe"], capture_output=True, timeout=10)
    time.sleep(1)

    # 3. Restore virgin original binary
    try:
        shutil.copy2(bak, ls)
        print(f"  {GREEN}[+] Бинарник {ls.name} успешно восстановлен из заводского бэкапа!{RESET}")
    except Exception as e:
        print(f"  {RED}[-] Ошибка восстановления: {e}{RESET}")
        return False

    print(f"\n{GREEN}{BOLD}[ГОТОВО] Antigravity возвращен к заводскому виду: оригинал на месте, авто-служба удалена.{RESET}")

    return True


def run_diagnostics():
    """Test connectivity and geo-eligibility to Google AI endpoints."""
    print(f"\n{BOLD}{CYAN}[*] Комплексная диагностика эндпоинтов Google AI и сети...{RESET}")

    egress = get_egress_info()
    print(f"  {WHITE}● Внешний IP (геобаза ipinfo, не определение Google): {CYAN}{egress}{RESET}")
    evidence = recent_location_error()
    if evidence:
        print(f"  {RED}● Последний ответ в логе Google: {evidence['reason']}, регион {evidence['detected_location']}, лог {evidence['log_time']}{RESET}")
    print("  Проверка корня HTTP подтверждает только соединение. 401/403/404 не подтверждают доступ к моделям.")

    endpoints = [
        ("CloudCode PA (Daily)", "https://daily-cloudcode-pa.googleapis.com"),
        ("CloudCode PA (Prod)", "https://cloudcode-pa.googleapis.com"),
        ("AI Code (FetchConfig)", "https://aicode.googleapis.com"),
        ("Generative Language", "https://generativelanguage.googleapis.com"),
        ("Gemini Web", "https://gemini.google.com"),
        ("Google Accounts", "https://accounts.google.com"),
    ]

    print(f"\n  {WHITE}{'Эндпоинт':<24} | {'HTTP Статус':<15} | {'Задержка':<10} | {'Вердикт':<20}{RESET}")
    print(f"  {DIM}{'-'*75}{RESET}")

    for name, url in endpoints:
        start_t = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=5) as res:
                dur = int((time.time() - start_t) * 1000)
                status_code = res.status
                verdict = http_verdict(status_code)
                print(f"  {WHITE}{name:<24}{RESET} | {status_code:<15} | {dur:<7} ms | {verdict}")
        except urllib.error.HTTPError as e:
            dur = int((time.time() - start_t) * 1000)
            try:
                verdict = http_verdict(e.code, e.read(64 * 1024).decode("utf-8", errors="replace"))
            except OSError:
                verdict = f"HTTP {e.code}; тело ответа не прочитано"
            finally:
                e.close()
            print(f"  {WHITE}{name:<24}{RESET} | {e.code:<15} | {dur:<7} ms | {verdict}")
        except Exception as e:
            dur = int((time.time() - start_t) * 1000)
            print(f"  {WHITE}{name:<24}{RESET} | {RED}Ошибка сети{RESET}     | {dur:<7} ms | {RED}{str(e)[:24]}{RESET}")

    print(f"\n{CYAN}{DIM}Диагностика завершена.{RESET}")


def install_watchdog():
    """Check both installations at logon with the source or portable executable."""
    print(f"\n{BOLD}{CYAN}[*] Установка автономного NoGravity Watchdog...{RESET}")
    script_path = Path(__file__).resolve()
    if getattr(sys, "frozen", False):
        task_exe = "powershell.exe"
        launch = f"Start-Process -FilePath '{sys.executable.replace(chr(39), chr(39) * 2)}' -ArgumentList '--apply-silent' -WindowStyle Hidden -Wait"
        task_args = subprocess.list2cmdline(["-NoProfile", "-WindowStyle", "Hidden", "-Command", launch])
    else:
        task_exe = str(Path(sys.executable).with_name("pythonw.exe"))
        task_args = subprocess.list2cmdline([str(script_path), "--apply-silent"])

    ps_install = f"""
    $a = New-ScheduledTaskAction -Execute '{task_exe.replace(chr(39), chr(39) * 2)}' -Argument '{task_args.replace(chr(39), chr(39) * 2)}';
    $t = New-ScheduledTaskTrigger -AtLogOn;
    $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries;
    Register-ScheduledTask -TaskName 'NoGravity Watchdog' -Action $a -Trigger $t -Settings $s -Force;
    """
    res = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_install], capture_output=True, text=True)
    if res.returncode == 0:
        print(f"{GREEN}[+] Задача 'NoGravity Watchdog' успешно зарегистрирована в планировщике!{RESET}")
        print("    При входе в Windows проверяется локальный патч Desktop и CLI; обновления не отслеживаются.")
        return True
    else:
        print(f"{RED}[-] Ошибка регистрации задачи: {res.stderr}{RESET}")
        return False


def main():
    parser = argparse.ArgumentParser(description="NoGravity 2.1.0 — Antigravity Desktop and CLI local patcher")
    actions = parser.add_mutually_exclusive_group()
    for name, short in [("apply", "a"), ("clean", "c"), ("revert", "r"), ("unwatch", "u"), ("watch", "w"), ("diag", "d"), ("status", "s")]:
        actions.add_argument("--" + name, "-" + short, action="store_true")
    actions.add_argument("--apply-silent", action="store_true")
    parser.add_argument("--target", choices=["all", "desktop", "cli"], default="all", help="Installation to patch or restore (default: all found)")
    args = parser.parse_args()
    if args.apply or args.apply_silent:
        sys.exit(0 if apply_targets(args.target, silent=args.apply_silent) else 1)
    if args.clean:
        sys.exit(0 if clean_conflicts() else 1)
    if args.revert:
        targets = get_targets(args.target)
        success = bool(targets)
        for name, path in targets:
            if not restore_factory_original(path):
                success = False
        sys.exit(0 if success else 1)
    if args.unwatch:
        sys.exit(0 if remove_watchdog() else 1)
    if args.watch:
        sys.exit(0 if install_watchdog() else 1)
    if args.diag:
        run_diagnostics()
        return
    if args.status:
        print(json.dumps(inspect_system(args.target), indent=2))
        return

    # Interactive TUI Loop
    while True:
        info = inspect_system(args.target)
        print_banner(info)

        wd_action = "Отключить авто-службу Watchdog" if info["watchdog_active"] else "Установить авто-службу Watchdog"
        print(f"""  {BOLD}{WHITE}[ МЕНЮ ДЕЙСТВИЙ ]{RESET}
  {CYAN}[1]{RESET} {BOLD}Применить локальный патч{RESET} (доступ Google проверяется отдельно)
  {CYAN}[2]{RESET} Очистить конфликты (Остановить сторонние демоны, снять задачи и NRPT)
  {CYAN}[3]{RESET} Заводской откат Antigravity (Восстановить оригинал + удалить авто-службу)
  {CYAN}[4]{RESET} Запустить диагностику Google AI эндпоинтов и сети
  {CYAN}[5]{RESET} {wd_action} (удержание патча при обновлениях)
  {CYAN}[0]{RESET} Выход
""")
        choice = input(f"  {BOLD}{WHITE}Выберите пункт [0-5]: {RESET}").strip()

        if choice == "1":
            apply_targets(args.target)
            input(f"\n{DIM}Нажмите Enter для продолжения...{RESET}")
        elif choice == "2":
            clean_conflicts()
            input(f"\n{DIM}Нажмите Enter для продолжения...{RESET}")
        elif choice == "3":
            for name, path in get_targets(args.target):
                restore_factory_original(path)
            input(f"\n{DIM}Нажмите Enter для продолжения...{RESET}")
        elif choice == "4":
            run_diagnostics()
            input(f"\n{DIM}Нажмите Enter для продолжения...{RESET}")
        elif choice == "5":
            if info["watchdog_active"]:
                remove_watchdog()
            else:
                install_watchdog()
            input(f"\n{DIM}Нажмите Enter для продолжения...{RESET}")
        elif choice == "0":
            print(f"\n{GREEN}Выход.{RESET}")
            sys.exit(0)
        else:
            print(f"\n{RED}Неверный ввод, повторите попытку.{RESET}")
            time.sleep(1)


if __name__ == "__main__":
    main()
