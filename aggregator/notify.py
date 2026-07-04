"""Windows toast notifications with a PowerShell fallback.

Primary: the `windows-toasts` package (WinRT). If it is unavailable or fails,
fall back to raw PowerShell using the WinRT ToastNotification XML API, which
needs no extra modules. Never raises -- a failed toast must not break the loop.
"""
from __future__ import annotations

import subprocess

try:  # optional dependency
    from windows_toasts import Toast, WindowsToaster  # type: ignore[import-not-found]

    _HAS_WINDOWS_TOASTS = True
except Exception:  # pragma: no cover - import guard
    _HAS_WINDOWS_TOASTS = False


def _toast_via_package(app_id: str, title: str, body: str) -> bool:
    try:
        toaster = WindowsToaster(app_id)
        toast = Toast()
        toast.text_fields = [title, body]
        toaster.show_toast(toast)
        return True
    except Exception:
        return False


def _ps_escape(text: str) -> str:
    return text.replace("'", "''")


def _toast_via_powershell(app_id: str, title: str, body: str) -> bool:
    """Raw WinRT toast through PowerShell. No BurntToast module required."""
    script = f"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null
$template = @"
<toast>
  <visual>
    <binding template="ToastGeneric">
      <text>{_ps_escape(title)}</text>
      <text>{_ps_escape(body)}</text>
    </binding>
  </visual>
</toast>
"@
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($template)
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{_ps_escape(app_id)}')
$notifier.Show($toast)
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0
    except Exception:
        return False


class Notifier:
    def __init__(self, app_id: str, enabled: bool = True):
        self.app_id = app_id
        self.enabled = enabled

    def send(self, title: str, body: str) -> bool:
        """Fire a toast. Returns True if some backend reported success."""
        if not self.enabled:
            return False
        if _HAS_WINDOWS_TOASTS and _toast_via_package(self.app_id, title, body):
            return True
        return _toast_via_powershell(self.app_id, title, body)


def backend_name() -> str:
    return "windows-toasts" if _HAS_WINDOWS_TOASTS else "powershell-winrt"
