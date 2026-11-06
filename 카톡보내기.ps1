<#
카카오톡 PC 채팅방에 메시지를 보낸다. 방이 닫혀 있으면 열어서 보내고 다시 닫는다.
다른 프로그램에서 작업 중이어도 되도록 키보드·마우스·클립보드를 쓰지 않고 창 메시지로만 조작한다.

  powershell -ExecutionPolicy Bypass -File 카톡보내기.ps1 -Room "테스트방" -Text "보낼 내용"
  powershell -ExecutionPolicy Bypass -File 카톡보내기.ps1 -Room "테스트방" -DryRun   # 열고 닫기만

안전장치
- 창 제목이 방 이름과 정확히 같은 창이 1개일 때만 보낸다. 엉뚱한 방이 열리면 닫고 멈춘다.
- 닫힌 방은 메인 창 검색 결과를 OCR로 읽어 제목이 맞는 줄을 연다(첫 줄이 다른 방일 수 있음). 방 열기는 카톡창_공통.ps1.
- 입력칸에 쓰던 글이 있으면 덮어쓰지 않는다. 넣은 문구가 정확히 같을 때만 Enter를 보내고, 입력칸이 비었는지 확인한다.
- 닫힌 방을 열면 카카오톡이 그 창을 앞으로 띄우므로, 곧바로 원래 쓰던 창으로 포커스를 되돌린다.
  (이 사이 1초 안쪽에 친 글자가 카톡 입력칸에 들어가면 위 검사에 걸려 보내지 않는다.)
- 메인 창이 '채팅' 탭이 아니거나 트레이에만 있으면 멈춘다.
#>
param(
  [Parameter(Mandatory)][string]$Room,
  [string]$Text,
  [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
if (-not $DryRun -and -not $Text) { throw '-Text 가 비어 있음 (열고 닫기만 하려면 -DryRun)' }
. "$PSScriptRoot\카톡창_공통.ps1"
$script:openedWin = [IntPtr]::Zero
$rm = $null
function Fail($msg) {
  if ($script:openedWin -ne [IntPtr]::Zero) { Close-Room $rm; $msg += ' / 연 창은 닫음' }
  try { Leave-Main } catch {}
  Restore-Focus
  Write-Output "중단: $msg"; exit 1
}
function Get-Input([IntPtr]$h) { # 빈 입력칸은 안내 문구 '메시지 입력'을 돌려준다
  $t = [KT]::Get($h) -replace "`r", ''
  if ($t -ceq '메시지 입력') { return '' } else { return $t }
}
function Set-Input([IntPtr]$h, [string]$t) { # EM_SETSEL 전체 + EM_REPLACESEL: 카톡이 입력으로 인식(전송 버튼 활성)
  [void][KT]::SendMessage($h, 0x00B1, [IntPtr]0, [IntPtr](-1)); [void][KT]::SendMessage($h, 0x00C2, [IntPtr]1, $t)
}

# 1) 방 창 찾기, 없으면 메인 창 검색으로 열기
try { $rm = Open-Room $Room } catch { Fail $_.Exception.Message }
$win = $rm.Win
$openedHere = $rm.OpenedHere
if ($openedHere) { $script:openedWin = $win }
$edit = @([KT]::Kids($win, 'RICHEDIT'))
if ($edit.Count -ne 1) { Fail "입력칸 $($edit.Count)개" }

# 2) 보내기
$result = '열기 확인 (전송 안 함)'
if (-not $DryRun) {
  $want = $Text -replace "`r", ''
  $draft = Get-Input $edit[0]
  if ($draft.Length -gt 0) { Fail "입력칸에 이미 글이 있음 (덮어쓰지 않음, 창은 열어둠): [$draft]" }
  Set-Input $edit[0] $want; Start-Sleep -Milliseconds 300
  $typed = Get-Input $edit[0]
  if ($typed -cne $want) { Set-Input $edit[0] ''; Fail "입력칸 내용이 다름 (지움): [$typed]" }
  [KT]::Key($edit[0], 0x0D, 0x1C); Start-Sleep -Milliseconds 900
  $left = Get-Input $edit[0]
  if ($left.Length -ne 0) { Fail "Enter 후에도 입력칸이 비지 않음 (전송 안 됐을 수 있음, 창은 열어둠): [$left]" }
  $result = "전송함: $Text"
}

# 3) 직접 연 창이면 닫기
if ($openedHere) { Close-Room $rm }
try { Leave-Main } catch {}
Restore-Focus
Write-Output "[$Room] $result$(if ($openedHere) { ' / 창 닫음' })"
