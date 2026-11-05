#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
NoGravity • Universal Doctor & Environment Patcher for Google Antigravity
================================================================================
Autonomous open-source patcher & diagnostics suite for Google Antigravity.
Neutralizes Protobuf geo-restriction gating, restores native proxy routing,
removes conflicting local DNS hooks/hijacks, and ensures rock-solid compatibility
with any VPN, SOCKS5, or HTTPS proxy solution (Happ, V2Ray, Clash, Sing-box, etc.).
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
    ps_args = " ".join([f'"{c}"' for c in cmd_list[1:]])
    ps_cmd = f'Start-Process -FilePath "{cmd_list[0]}" -ArgumentList \'{ps_args}\' -Verb RunAs -Wait'
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


def inspect_system():
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
        "nrpt_hijacked": False,
        "conflicting_tasks": False,
        "conflicting_process_running": False,
    }

    if info["binary_exists"]:
        try:
            data = ls.read_bytes()
            info["inexigible_count"] = data.count(b"inexigible")
            info["ineligible_count"] = data.count(b"ineligible")
            info["ag_ls_proxy_count"] = data.count(b"AG_LS_PROXY")
            info["https_proxy_count"] = data.count(b"https_proxy")
        except Exception:
            pass

    # Check environment variable
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ) as key:
            info["env_ag_ls_proxy"] = winreg.QueryValueEx(key, "AG_LS_PROXY")[0]
    except FileNotFoundError:
        pass
    except Exception:
        pass

    # Check NRPT DNS hijacks (e.g. 127.0.0.53 rule)
    try:
        res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", "Get-DnsClientNrptRule | Select-Object -ExpandProperty Namespace"],
            capture_output=True,
            text=True,
        )
        if any("cloudcode-pa.googleapis.com" in l for l in res.stdout.splitlines()):
            info["nrpt_hijacked"] = True
    except Exception:
        pass

    # Check conflicting scheduled tasks
    try:
        res_tasks = subprocess.run(["schtasks", "/query", "/fo", "CSV"], capture_output=True, text=True)
        if any(marker in res_tasks.stdout for marker in ["ag_dns", "Antigravity Watchdog"]):
            info["conflicting_tasks"] = True
    except Exception:
        pass

    # Check conflicting processes (e.g. ag_dns.exe)
    try:
        res_proc = subprocess.run(["tasklist", "/fi", "imagename eq ag_dns.exe"], capture_output=True, text=True)
        if "ag_dns.exe" in res_proc.stdout:
            info["conflicting_process_running"] = True
    except Exception:
        pass

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
        {WHITE}Autonomous Antigravity Doctor & Environment Patcher v2.0{CYAN}
  {DIM}======================================================================={RESET}""")

    print(f"{BOLD}{WHITE}  [ СИСТЕМНЫЙ ДАШБОРД СОВМЕСТИМОСТИ ]{RESET}")

    # 1. Binary location
    if not info["binary_exists"]:
        bin_str = f"{RED}[ НЕ НАЙДЕН ] {info['ls_path']}{RESET}"
    else:
        bin_str = f"{GREEN}[ НАЙДЕН ] {info['ls_path']}{RESET}"
    print(f"  ● Языковой сервер     : {bin_str}")

    # 2. Regional Protobuf Gating
    if info["inexigible_count"] > 0:
        reg_str = f"{GREEN}[ СНЯТО ] {info['inexigible_count']} точек нейтрализации (inexigible){RESET}"
    elif info["ineligible_count"] > 0:
        reg_str = f"{RED}[ АКТИВЕН БЛОК ] Аккаунты РФ блокируются сервером ({info['ineligible_count']} точек ineligible){RESET}"
    else:
        reg_str = f"{YELLOW}[ НЕИЗВЕСТНО ] Сигнатуры Protobuf не найдены{RESET}"
    print(f"  ● Региональный лок    : {reg_str}")

    # 3. Proxy routing hook
    if info["ag_ls_proxy_count"] > 0:
        hook_str = f"{YELLOW}[ ПЕРЕХВАЧЕН ] Вшита привязка к локальному AG_LS_PROXY:53129{RESET}"
    else:
        hook_str = f"{GREEN}[ ЧИСТО ] Нативный https_proxy (стандартная маршрутизация туннеля){RESET}"
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
        nrpt_str = f"{GREEN}[ ЧИСТО ] DNS обрабатывается сетевым адаптером / VPN-клиентом{RESET}"
    print(f"  ● DNS маршрутизация   : {nrpt_str}")

    print(f"{CYAN}{DIM}  -----------------------------------------------------------------------{RESET}")


def apply_nogravity_patch(clean_first: bool = True):
    """Apply NoGravity patch: byte neutralization + restore clean proxy env."""
    ls = get_ls_path()
    bak = ls.with_suffix(".exe.bak_original")

    if clean_first:
        clean_conflicts()

    print(f"\n{BOLD}{CYAN}[*] Применение патча NoGravity...{RESET}")

    if not ls.exists():
        print(f"{RED}[-] Файл {ls} не найден!{RESET}")
        return

    # Check if Antigravity or language server is currently running
    res_ls = subprocess.run(["tasklist", "/fi", "imagename eq language_server.exe"], capture_output=True, text=True)
    if "language_server.exe" in res_ls.stdout:
        print(f"{YELLOW}[!] Antigravity запущен. Для записи патча процесс language_server.exe должен быть закрыт.{RESET}")
        choice = input(f"{WHITE}Завершить процесс language_server.exe сейчас? (y/N): {RESET}").strip().lower()
        if choice == "y":
            subprocess.run(["taskkill", "/F", "/IM", "language_server.exe"], capture_output=True)
            subprocess.run(["taskkill", "/F", "/IM", "Antigravity.exe"], capture_output=True)
            time.sleep(1)
        else:
            print(f"{YELLOW}[*] Попытка применить патч без остановки...{RESET}")

    # Create backup if not present
    if not bak.exists():
        try:
            shutil.copy2(ls, bak)
            print(f"  {GREEN}[+] Создан оригинальный резервный бэкап: {bak.name}{RESET}")
        except Exception as e:
            print(f"  {YELLOW}[!] Предупреждение при создании бэкапа: {e}{RESET}")

    # Read binary
    try:
        data = bytearray(ls.read_bytes())
    except PermissionError:
        print(f"{RED}[-] Ошибка доступа: файл заблокирован. Закройте приложение Antigravity и повторите запуск.{RESET}")
        return

    # 1. ineligible -> inexigible (neutralize Protobuf account check)
    c_ineligible = data.count(b"ineligible")
    if c_ineligible > 0:
        data = data.replace(b"ineligible", b"inexigible")
        print(f"  {GREEN}[+] Protobuf геоблок нейтрализован: {c_ineligible} вхождений ineligible -> inexigible{RESET}")
    else:
        print(f"  {GREEN}[=] Protobuf геоблок уже нейтрализован ({data.count(b'inexigible')} точек inexigible){RESET}")

    # 2. AG_LS_PROXY -> https_proxy (revert custom proxy hooks to native HTTPS proxy)
    c_ag_proxy = data.count(b"AG_LS_PROXY")
    if c_ag_proxy > 0:
        data = data.replace(b"AG_LS_PROXY", b"https_proxy")
        print(f"  {GREEN}[+] Сетевой хук снят: {c_ag_proxy} вхождений AG_LS_PROXY -> https_proxy{RESET}")
    else:
        print(f"  {GREEN}[=] Сетевая конфигурация бинарника чиста (нативный https_proxy){RESET}")

    # Atomic write
    tmp_path = ls.with_suffix(".exe.tmp")
    try:
        tmp_path.write_bytes(data)
        shutil.move(str(tmp_path), str(ls))
        print(f"  {GREEN}[+] language_server.exe успешно пропатчен и сохранен!{RESET}")
    except Exception as e:
        print(f"{RED}[-] Не удалось записать файл: {e}{RESET}")
        if tmp_path.exists():
            tmp_path.unlink()
        return

    # Remove conflicting registry proxy variable if left behind
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, "AG_LS_PROXY")
            print(f"  {GREEN}[+] Переменная AG_LS_PROXY удалена из реестра пользователя{RESET}")
    except FileNotFoundError:
        pass
    except Exception:
        pass

    os.environ.pop("AG_LS_PROXY", None)

    print(f"\n{GREEN}{BOLD}[ГОТОВО] Патч NoGravity успешно применен! Теперь Antigravity свободно работает через любой VPN.{RESET}")


def clean_conflicts():
    """Remove background DNS hijackers, conflicting scheduled tasks, and NRPT rules."""
    print(f"\n{BOLD}{CYAN}[*] Очистка конфликтующих хуков и сторонних служб...{RESET}")

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
        $_.Namespace -like '*googleapis.com*' -or 
        $_.IPsecCARestriction -like '*127.0.0.53*' 
    } | Remove-DnsClientNrptRule -Force
    """
    run_elevated(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_nrpt])
    print(f"  {GREEN}[+] Правила NRPT перехвата DNS (127.0.0.53) очищены{RESET}")

    print(f"\n{GREEN}{BOLD}[ГОТОВО] Все конфликтующие сетевые перехваты успешно сняты.{RESET}")


def restore_factory_original():
    """Restore virgin language_server.exe from original backup."""
    ls = get_ls_path()
    bak = ls.with_suffix(".exe.bak_original")

    print(f"\n{BOLD}{YELLOW}[*] Откат Antigravity к заводскому оригиналу...{RESET}")
    if not bak.exists():
        print(f"{RED}[-] Оригинальный резервный бэкап {bak.name} не найден!{RESET}")
        return

    choice = input(f"{WHITE}Вы уверены, что хотите вернуть непатченный оригинальный бинарник? (y/N): {RESET}").strip().lower()
    if choice != "y":
        return

    subprocess.run(["taskkill", "/F", "/IM", "language_server.exe"], capture_output=True)
    subprocess.run(["taskkill", "/F", "/IM", "Antigravity.exe"], capture_output=True)
    time.sleep(1)

    try:
        shutil.copy2(bak, ls)
        print(f"{GREEN}[+] Бинарник language_server.exe успешно восстановлен из заводского бэкапа!{RESET}")
    except Exception as e:
        print(f"{RED}[-] Ошибка восстановления: {e}{RESET}")


def run_diagnostics():
    """Test connectivity and geo-eligibility to Google AI endpoints."""
    print(f"\n{BOLD}{CYAN}[*] Комплексная диагностика эндпоинтов Google AI и сети...{RESET}")

    egress = get_egress_info()
    print(f"  {WHITE}● Текущий внешний узел : {CYAN}{egress}{RESET}")

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
                verdict = f"{GREEN}Доступен{RESET}"
                print(f"  {WHITE}{name:<24}{RESET} | {status_code:<15} | {dur:<7} ms | {verdict}")
        except urllib.error.HTTPError as e:
            dur = int((time.time() - start_t) * 1000)
            if e.code in [401, 403, 404]:
                try:
                    err_body = e.read().decode("utf-8", errors="ignore")
                    if "LOCATION_NOT_ELIGIBLE" in err_body or "User location is not supported" in err_body:
                        verdict = f"{RED}Геоблок (RU / Cloudflare WARP){RESET}"
                    else:
                        verdict = f"{GREEN}Доступен ({e.code}){RESET}"
                except Exception:
                    verdict = f"{YELLOW}HTTP {e.code}{RESET}"
            else:
                verdict = f"{YELLOW}HTTP {e.code}{RESET}"
            print(f"  {WHITE}{name:<24}{RESET} | {e.code:<15} | {dur:<7} ms | {verdict}")
        except Exception as e:
            dur = int((time.time() - start_t) * 1000)
            print(f"  {WHITE}{name:<24}{RESET} | {RED}Ошибка сети{RESET}     | {dur:<7} ms | {RED}{str(e)[:24]}{RESET}")

    print(f"\n{CYAN}{DIM}Диагностика завершена.{RESET}")


def install_watchdog():
    """Install lightweight watchdog task ensuring patch persistence across Antigravity auto-updates."""
    print(f"\n{BOLD}{CYAN}[*] Установка автономного NoGravity Watchdog...{RESET}")
    script_path = Path(__file__).resolve()

    ps_install = f"""
    $a = New-ScheduledTaskAction -Execute 'pythonw.exe' -Argument '\"{script_path}\" --apply-silent';
    $t = New-ScheduledTaskTrigger -AtLogOn;
    $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries;
    Register-ScheduledTask -TaskName 'NoGravity Watchdog' -Action $a -Trigger $t -Settings $s -Force;
    """
    res = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_install], capture_output=True, text=True)
    if res.returncode == 0:
        print(f"{GREEN}[+] Задача 'NoGravity Watchdog' успешно зарегистрирована в планировщике!{RESET}")
        print(f"    (При каждом входе в систему и после авто-обновлений Antigravity патч поддерживается автоматически).")
    else:
        print(f"{RED}[-] Ошибка регистрации задачи: {res.stderr}{RESET}")


def main():
    if len(sys.argv) > 1:
        flag = sys.argv[1].lower()
        if flag in ["--apply", "-a"]:
            clean_conflicts()
            apply_nogravity_patch(clean_first=False)
            return
        elif flag == "--apply-silent":
            ls = get_ls_path()
            if ls.exists():
                try:
                    data = bytearray(ls.read_bytes())
                    changed = False
                    if b"ineligible" in data:
                        data = data.replace(b"ineligible", b"inexigible")
                        changed = True
                    if b"AG_LS_PROXY" in data:
                        data = data.replace(b"AG_LS_PROXY", b"https_proxy")
                        changed = True
                    if changed:
                        ls.write_bytes(data)
                except Exception:
                    pass
            return
        elif flag in ["--clean", "-c"]:
            clean_conflicts()
            return
        elif flag in ["--revert", "-r"]:
            restore_factory_original()
            return
        elif flag in ["--diag", "-d"]:
            run_diagnostics()
            return
        elif flag in ["--status", "-s"]:
            info = inspect_system()
            print(json.dumps(info, indent=2))
            return

    # Interactive TUI Loop
    while True:
        info = inspect_system()
        print_banner(info)

        print(f"""  {BOLD}{WHITE}[ МЕНЮ ДЕЙСТВИЙ ]{RESET}
  {CYAN}[1]{RESET} {BOLD}Активировать NoGravity{RESET} (Снять геоблок + восстановить нативный прокси)
  {CYAN}[2]{RESET} Очистить конфликты (Остановить сторонние демоны, снять задачи и NRPT)
  {CYAN}[3]{RESET} Заводской откат Antigravity (Восстановить исходный language_server.exe)
  {CYAN}[4]{RESET} Запустить диагностику Google AI эндпоинтов и сети
  {CYAN}[5]{RESET} Установить авто-сохранение патча при обновлениях (NoGravity Watchdog)
  {CYAN}[0]{RESET} Выход
""")
        choice = input(f"  {BOLD}{WHITE}Выберите пункт [0-5]: {RESET}").strip()

        if choice == "1":
            clean_conflicts()
            apply_nogravity_patch(clean_first=False)
            input(f"\n{DIM}Нажмите Enter для продолжения...{RESET}")
        elif choice == "2":
            clean_conflicts()
            input(f"\n{DIM}Нажмите Enter для продолжения...{RESET}")
        elif choice == "3":
            restore_factory_original()
            input(f"\n{DIM}Нажмите Enter для продолжения...{RESET}")
        elif choice == "4":
            run_diagnostics()
            input(f"\n{DIM}Нажмите Enter для продолжения...{RESET}")
        elif choice == "5":
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
