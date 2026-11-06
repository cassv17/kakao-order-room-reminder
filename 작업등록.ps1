<#
오더방 감시를 Windows 작업 스케줄러에 등록한다: 월~토 09:00~19:30, 5분마다. 이 폴더에서 실행한다.

  powershell -ExecutionPolicy Bypass -File 작업등록.ps1            # 테스트 모드(보내지 않고 알림만)
  powershell -ExecutionPolicy Bypass -File 작업등록.ps1 -Auto     # 자동 전송 모드(회신 없으면 바로 보낸다)
  powershell -ExecutionPolicy Bypass -File 작업등록.ps1 -Remove   # 등록 해제

Windows에 로그인해 있을 때만 돈다(카톡 화면을 읽으므로). Python 3.10 이상이 필요하다.
#>
param([switch]$Auto, [switch]$Remove, [string]$Name = '오더방 감시')
$ErrorActionPreference = 'Stop'
if ($Remove) { Unregister-ScheduledTask -TaskName $Name -Confirm:$false; "해제함: $Name"; return }
foreach ($f in '설정.json', '오더방_목록.md') { if (-not (Test-Path (Join-Path $PSScriptRoot $f))) { throw "$f 가 없습니다. 예시 파일을 복사해 먼저 만드세요 (README 참고)." } }
$py = (Get-Command pythonw.exe -ErrorAction Stop).Source
$arg = '-I "' + (Join-Path $PSScriptRoot '오더방_감시.py') + '"' + $(if ($Auto) { ' --auto' } else { '' })
$act = New-ScheduledTaskAction -Execute $py -Argument $arg -WorkingDirectory $PSScriptRoot
$trg = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday, Saturday -At '09:00'
$trg.Repetition = (New-ScheduledTaskTrigger -Once -At '09:00' -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Hours 10 -Minutes 31)).Repetition
$set = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$pri = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$mode = if ($Auto) { '자동 전송' } else { '테스트 모드' }
Register-ScheduledTask -TaskName $Name -Description "카톡 오더방 미회신 리마인드 ($mode)" -Action $act -Trigger $trg -Settings $set -Principal $pri -Force | Out-Null
"등록함: $Name ($mode) — 다음 실행 $((Get-ScheduledTaskInfo -TaskName $Name).NextRunTime)"
