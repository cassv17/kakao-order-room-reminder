<#
오더방 감시용 창 조작. 결과는 -Out 파일(UTF-8)에 탭 구분 줄로 쓴다. 오더방_감시.py가 부른다.

  -Action list  -Pages 2                      메인 창 채팅 목록을 위에서부터 Pages 화면 OCR
  -Action list  -NoScroll                     목록을 건드리지 않고 지금 보이는 한 화면만 OCR (상시 감시용)
      출력: L <page> <x> <y> <text>
  -Action scan  -Title "<방 제목>" -StopDate 2026-11-05 -MaxPages 12
      방을 (닫혀 있으면 열어서) 맨 아래로 내린 뒤 위로 올리며 OCR. StopDate 이하 날짜 구분선이 보이면 멈춘다.
      출력: M <listTop> <listBottom> <openedHere> / P <page> <x> <y> <text>
  -Action probe -Title "<방 제목(근사값)>" -MaxPages 8   (설치용) scan과 같되 열린 창의 실제 제목을 'T <제목>' 줄로 먼저 낸다
방을 열면 그 방은 읽음 처리된다. 직접 연 방은 화면 밖에서 읽고, 원래 위치로 되돌려 닫는다.
#>
param(
  [Parameter(Mandatory)][ValidateSet('list', 'scan', 'probe')][string]$Action,
  [Parameter(Mandatory)][string]$Out,
  [string]$Title, [string]$StopDate, [int]$Pages = 2, [int]$MaxPages = 12, [int]$Ticks = 1,
  [switch]$NoScroll,
  [string]$KeepDir   # 진단용: 캡처 이미지를 이 폴더에 남긴다
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\카톡창_공통.ps1"
$tmp = if ($KeepDir) { $KeepDir } else { Join-Path $env:TEMP ('odr_' + [guid]::NewGuid().ToString('N')) }
New-Item -ItemType Directory -Force $tmp | Out-Null
$lines = New-Object System.Collections.Generic.List[string]
Add-Type -AssemblyName System.Windows.Forms
# 선택된 칩(검은 배경)을 찾는다: 전체(맨 앞)·안읽음(둘째)이면 통과, 다른 칩이면 반전해 읽어 '오더방'일 때만 통과
function Assert-ChipTab([string]$png, [string]$dir) {
  $bmp = [Drawing.Bitmap]::FromFile($png)
  try {
    $cl = @(); $cur = $null
    for ($x = 96; $x -lt [Math]::Min(990, $bmp.Width - 4); $x += 2) {
      $d = 0; foreach ($y in 108, 118, 128) { $c = $bmp.GetPixel($x, $y); if (($c.R + $c.G + $c.B) / 3 -lt 70) { $d++ } }
      if ($d -ge 2) { if ($cur -and ($x - $cur[1]) -le 8) { $cur[1] = $x } else { $cur = @($x, $x); $cl += , $cur } }
    }
    $sel = @($cl | Where-Object { ($_[1] - $_[0]) -ge 40 }) | Select-Object -First 1
    if (-not $sel) { throw '메인 창 탭 줄을 읽지 못함 (선택된 칩이 안 보임)' }
    if ($sel[0] -le 125) { return }   # 전체
    if ($sel[0] -ge 150 -and $sel[0] -le 215) { return }   # 안읽음(둘째 칩): 안 읽은 방만 보이지만 새 문의는 읽기 전이라 목록에 올라온다
    $w = $sel[1] - $sel[0] + 8
    $crop = New-Object Drawing.Bitmap $w, 36
    for ($i = 0; $i -lt $w; $i++) { for ($j = 0; $j -lt 36; $j++) { $c = $bmp.GetPixel([Math]::Min($bmp.Width - 1, $sel[0] - 4 + $i), 100 + $j); $crop.SetPixel($i, $j, [Drawing.Color]::FromArgb(255 - $c.R, 255 - $c.G, 255 - $c.B)) } }
    $cp = Join-Path $dir 'chip.png'; $crop.Save($cp); $crop.Dispose()
  } finally { $bmp.Dispose() }
  $txt = (Invoke-Ocr $cp | ForEach-Object { $_.Text }) -join ' '
  if ($txt -notmatch '오더') { throw "사용 중: 메인 창이 전체·안읽음·오더방 탭이 아님 (선택된 탭: $txt)" }
}
function Emit([string]$s) { $lines.Add($s) }
# Windows OCR은 확대 배율에 따라 줄 하나(말풍선 옆 시각, 보낸 사람 줄 등)를 통째로 빠뜨리는 일이 있다 → 두 배율로 읽어 빠진 줄을 보탠다.
# 글자 조각이 섞이지 않게, 첫 배율에 없는 높이의 줄과 시각 줄만 보탠다
function Invoke-RoomOcr([string]$png) {
  $all = @(Invoke-Ocr $png)
  $time = '^(\d+\s+)?(오전|오후)\s*\d{1,2}\s*\D?\s*\d{2}$'
  foreach ($b in @(Invoke-Ocr $png 1.5)) {
    $same = @(if ($b.Text -match $time) { @($all | Where-Object { $_.Text -match $time -and [Math]::Abs($_.Y - $b.Y) -le 12 }) }
            else { @($all | Where-Object { [Math]::Abs($_.Y - $b.Y) -le 7 }) })   # 바깥 @()가 없으면 5.1에서 1건의 Count가 비어 중복이 들어간다
    if (-not $same.Count) { $all += $b }
  }
  $all
}
# 창을 키운 직후에는 대화 목록 아래쪽이 하얗게 빈 채 찍히기도 한다 (왼쪽 가장자리: 가운데는 배경색인데 맨 아래만 순백)
function Test-Unpainted([string]$png, [int]$top, [int]$bottom) {
  $bmp = [Drawing.Bitmap]::FromFile($png)
  try {
    $w = @(($bottom - 4), [int](($top + $bottom) / 2) | ForEach-Object { $c = $bmp.GetPixel(6, $_); $c.R -gt 250 -and $c.G -gt 250 -and $c.B -gt 250 })
    $w[0] -and -not $w[1]
  } finally { $bmp.Dispose() }
}
function Save-Room([IntPtr]$h, [string]$png, [int]$top, [int]$bottom) {
  for ($k = 0; $k -lt 8; $k++) {
    $f = Save-Print $h $png
    if (-not (Test-Unpainted $f $top $bottom)) { return $f }
    Start-Sleep -Milliseconds 500
  }
  throw '방 화면 아래쪽이 다 그려지지 않음 — 다음 회차에 다시 읽음'
}
function Hash([string]$p) { $b = [IO.File]::ReadAllBytes($p); [BitConverter]::ToString((New-Object Security.Cryptography.MD5CryptoServiceProvider).ComputeHash($b)) }

try {
  if ($Action -eq 'list') {
    $main = Get-Main
    if ($NoScroll) {
      # 상시 감시: 메인 창을 화면 밖에서 넓고 길게 만들어 목록 위쪽 두 화면을 읽고 원래대로 돌려놓는다.
      # 칩(전체·오더방…)은 건드리지 않는다. 전체 탭이든 오더방 탭이든 새 글이 온 방이 위로 올라온다.
      Assert-NotBusy
      # 사용자가 검색창에 글자를 입력해 둔 상태면 목록 대신 검색 결과가 보이고 탭 칩도 없다 → 실패가 아니라 '사용 중'
      $lv0 = Get-ListView $main
      $sb = @([KT]::Kids($lv0, 'Edit') | Where-Object { [KT]::GetParent($_) -eq $lv0 })
      if ($sb.Count -eq 1 -and (([KT]::Txt($sb[0]) + [KT]::Get($sb[0])).Trim())) { throw '사용 중: 카톡 검색창에 글자가 있음' }
      Hold-Main $main
      [void](Hide-Win $main)
      $x = [System.Windows.Forms.SystemInformation]::VirtualScreen.Right + 200
      [void][KT]::SetWindowPos($main, [IntPtr]::Zero, $x, 0, 1000, 1372, 0x0014)
      Start-Sleep -Milliseconds 1200
      $lv = Get-ListView $main
      $lc = @([KT]::Kids($lv, 'EVA_VH_ListControl'))[0]
      $r = Get-Rect $lc; $cx = [int](($r.L + $r.R) / 2); $cy = [int](($r.T + $r.B) / 2)
      [KT]::Wheel($lc, 120, 40, $cx, $cy); Start-Sleep -Milliseconds 500
      $f = Save-Print $main (Join-Path $tmp 'list_1.png')
      Assert-ChipTab $f $tmp
      foreach ($l in (Invoke-Ocr $f)) { Emit "L`t1`t$($l.X)`t$($l.Y)`t$($l.Text)" }
      $rows = [Math]::Max(4, [int](($r.B - $r.T) / 87) - 1)   # 한 화면의 방 수보다 1 적게 내려 한 줄 겹치게
      [KT]::Wheel($lc, -120, $rows, $cx, $cy); Start-Sleep -Milliseconds 700
      $f2 = Save-Print $main (Join-Path $tmp 'list_2.png')
      foreach ($l in (Invoke-Ocr $f2)) { Emit "L`t2`t$($l.X)`t$($l.Y)`t$($l.Text)" }
      [KT]::Wheel($lc, 120, 40, $cx, $cy)
      Emit 'OK'; return
    }
    $lv = Get-ListView $main
    $lc = @([KT]::Kids($lv, 'EVA_VH_ListControl'))[0]
    $r = Get-Rect $lc; $cx = [int](($r.L + $r.R) / 2); $cy = [int](($r.T + $r.B) / 2)
    $rowTicks = 6   # 한 칸 = 한 방, 한 화면 7줄 → 6칸씩 내려 1줄 겹침
    [KT]::Wheel($lc, 120, 80, $cx, $cy); Start-Sleep -Milliseconds 500
    $prev = $null
    for ($p = 1; $p -le $Pages; $p++) {
      $f = Save-Print $main (Join-Path $tmp "list_$p.png")
      $h = Hash $f; if ($h -eq $prev) { break }; $prev = $h
      foreach ($l in (Invoke-Ocr $f)) { Emit "L`t$p`t$($l.X)`t$($l.Y)`t$($l.Text)" }
      [KT]::Wheel($lc, -120, $rowTicks, $cx, $cy); Start-Sleep -Milliseconds 600
    }
    [KT]::Wheel($lc, 120, 80, $cx, $cy)
  }
  else {
    if (-not $Title) { throw '-Title 필요' }
    $stop = if ($StopDate) { [datetime]::ParseExact($StopDate, 'yyyy-MM-dd', $null) } else { [datetime]::Today }
    $room = Open-Room $Title $tmp -Probe:($Action -eq 'probe')
    $win = $room.Win
    if ($Action -eq 'probe') { Emit "T`t$([KT]::Txt($win))"; $stop = [datetime]'2000-01-01' }   # 날짜 구분선으로 멈추지 않고 MaxPages까지 읽는다
    try {
      if ($room.OpenedHere) {
        # 화면 밖으로 옮겨진 창을 세로로 키워 긴 문의 글도 한 화면에 들어오게 한다 (닫을 때 Close-Room이 되돌림)
        $cur = Get-Rect $win
        [void][KT]::SetWindowPos($win, [IntPtr]::Zero, $cur.L, 0, ($cur.R - $cur.L), 1300, 0x0014)
        Start-Sleep -Milliseconds 500
      }
      $lc = @([KT]::Kids($win, 'EVA_VH_ListControl'))[0]
      $wr = Get-Rect $win; $r = Get-Rect $lc
      $cx = [int](($r.L + $r.R) / 2); $cy = [int](($r.T + $r.B) / 2)
      $listH = $r.B - $r.T
      $ticks = [Math]::Max(1, $Ticks)   # 한 칸(약 120px)씩만 올린다: 문의 글 하나가 500px 넘게 길 수 있어 큰 간격이면 어느 화면에도 통째로 안 들어오고, 날짜 구분선도 놓친다
      Emit "M`t$($r.T - $wr.T)`t$($r.B - $wr.T)`t$($room.OpenedHere)"
      [KT]::Wheel($lc, -120, 120, $cx, $cy); Start-Sleep -Milliseconds 700   # 맨 아래로
      $prev = $null; $why = 'max'
      for ($p = 1; $p -le $MaxPages; $p++) {
        $png = Join-Path $tmp "room_$p.png"
        $f = if ($p -eq 1) { Save-Room $win $png ($r.T - $wr.T) ($r.B - $wr.T) } else { Save-Print $win $png }   # 첫 화면(맨 아래)은 다 그려진 것만 쓴다
        $h = Hash $f
        if ($h -eq $prev) {   # 같은 화면: 정말 맨 위일 수도, 스크롤이 아직 안 먹었을 수도 있다 → 조금 더 올려 한 번 더 확인
          [KT]::Wheel($lc, 120, 3, $cx, $cy); Start-Sleep -Milliseconds 1000
          $f = Save-Print $win (Join-Path $tmp "room_$p.png"); $h = Hash $f
          if ($h -eq $prev) { $why = 'top'; break }   # 맨 위에 닿음
        }
        $prev = $h
        $hit = $false
        foreach ($l in (Invoke-RoomOcr $f)) {
          Emit "P`t$p`t$($l.X)`t$($l.Y)`t$($l.Text)"
          if ($l.Text -match '(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일') {
            try { if ((Get-Date -Year $matches[1] -Month $matches[2] -Day $matches[3]).Date -le $stop) { $hit = $true } } catch {}
          }
        }
        if ($hit) { $why = 'stop'; break }
        [KT]::Wheel($lc, 120, $ticks, $cx, $cy); Start-Sleep -Milliseconds 700
      }
      Emit "E`t$why"   # stop=기준 날짜 구분선까지 읽음 / top=방 맨 위까지 읽음 / max=MaxPages에서 멈춤(덜 읽음)
      [KT]::Wheel($lc, -120, 120, $cx, $cy)
    } finally {
      Close-Room $room
      Restore-Focus
    }
  }
  Emit 'OK'
} catch {
  Emit "ERR`t$($_.Exception.Message)"
} finally {
  try { Leave-Main } catch {}
  [IO.File]::WriteAllLines($Out, $lines, (New-Object Text.UTF8Encoding $false))
  if (-not $KeepDir) { Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue }
}
