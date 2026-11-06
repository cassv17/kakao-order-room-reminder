param([string]$Title = "오더방", [string]$Message = "")
# Windows 토스트 알림. scenario='reminder' + 시스템 '확인' 버튼: 사용자가 확인을 누르기 전에는 사라지지 않는다.
$ErrorActionPreference = "Stop"
try {
  [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
  [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
  $esc = { param($s) [System.Security.SecurityElement]::Escape($s) }
  $xml = "<toast scenario='reminder'><visual><binding template='ToastGeneric'><text>$(& $esc $Title)</text><text>$(& $esc $Message)</text></binding></visual><actions><action content='확인' arguments='dismiss' activationType='system'/></actions></toast>"
  $doc = New-Object Windows.Data.Xml.Dom.XmlDocument
  $doc.LoadXml($xml)
  $appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
  [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show((New-Object Windows.UI.Notifications.ToastNotification $doc))
  "toast ok"
} catch {
  Add-Type -AssemblyName System.Windows.Forms
  $n = New-Object System.Windows.Forms.NotifyIcon
  $n.Icon = [System.Drawing.SystemIcons]::Information
  $n.Visible = $true
  $n.ShowBalloonTip(15000, $Title, $Message, [System.Windows.Forms.ToolTipIcon]::Warning)
  Start-Sleep -Seconds 16
  $n.Dispose()
  "balloon fallback: $($_.Exception.Message)"
}
