# 카카오톡 PC 창 조작 공통 함수 (dot-source 해서 쓴다: . "$PSScriptRoot\카톡창_공통.ps1")
# 키보드·마우스 커서·클립보드를 쓰지 않고 창 메시지(SendMessage/PostMessage)로만 조작한다.
# 좌표는 모두 물리 픽셀이다(SetProcessDPIAware). PrintWindow 캡처 이미지 좌표와 같다.
Add-Type -AssemblyName System.Drawing
if (-not ('KT' -as [type])) { Add-Type @'
using System; using System.Text; using System.Runtime.InteropServices; using System.Collections.Generic;
public struct KR { public int L,T,R,B; }
public class KT {
 public delegate bool P(IntPtr h, IntPtr l);
 [DllImport("user32.dll")] static extern bool EnumWindows(P p, IntPtr l);
 [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr w, P p, IntPtr l);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
 [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
 [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, IntPtr pid);
 [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
 [DllImport("user32.dll")] static extern bool AttachThreadInput(uint a, uint b, bool f);
 [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
 [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
 public struct WP { public int length, flags, showCmd, pMinX, pMinY, pMaxX, pMaxY, L, T, R, B; }
 [DllImport("user32.dll")] static extern bool GetWindowPlacement(IntPtr h, ref WP p);
 [DllImport("user32.dll")] static extern bool SetWindowPlacement(IntPtr h, ref WP p);
 public static int[] Normal(IntPtr h){ var p=new WP(); p.length=Marshal.SizeOf(typeof(WP)); GetWindowPlacement(h, ref p); return new int[]{p.L,p.T,p.R,p.B}; }
 public static void Place(IntPtr h, int show, int l, int t, int r, int b){ var p=new WP(); p.length=Marshal.SizeOf(typeof(WP)); GetWindowPlacement(h, ref p); p.showCmd=show; p.L=l; p.T=t; p.R=r; p.B=b; SetWindowPlacement(h, ref p); }
 public static IntPtr WaitMove(uint pid, string title, long[] before, int timeoutMs, int x, out KR orig){
   orig = new KR(); var sw = System.Diagnostics.Stopwatch.StartNew();
   while (sw.ElapsedMilliseconds < timeoutMs) {
     foreach (var h in Tops(pid)) {
       if (Array.IndexOf(before, (long)h) >= 0 || Txt(h) != title) continue;
       KR r; GetWindowRect(h, out r); orig = r;
       SetWindowPos(h, IntPtr.Zero, x, 0, r.R - r.L, r.B - r.T, 0x0014);
       return h;
     }
     System.Threading.Thread.Sleep(3);
   }
   return IntPtr.Zero; }
 public static void Click(IntPtr h, int x, int y){ IntPtr lp=(IntPtr)(((y&0xFFFF)<<16)|(x&0xFFFF)); PostMessage(h,0x0200,IntPtr.Zero,lp); System.Threading.Thread.Sleep(60); PostMessage(h,0x0201,(IntPtr)1,lp); System.Threading.Thread.Sleep(40); PostMessage(h,0x0202,IntPtr.Zero,lp); }
 public struct LII { public uint cb; public uint t; }
 [DllImport("user32.dll")] static extern bool GetLastInputInfo(ref LII i);
 public static uint IdleMs(){ var i=new LII(); i.cb=8; GetLastInputInfo(ref i); return unchecked((uint)Environment.TickCount - i.t); }
 [DllImport("user32.dll")] public static extern IntPtr GetParent(IntPtr h);
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out KR r);
 [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
 [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint f);
 [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr SendMessage(IntPtr h, uint m, IntPtr w, string l);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr SendMessage(IntPtr h, uint m, IntPtr w, StringBuilder l);
 [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
 static string Cls(IntPtr h){ var c=new StringBuilder(128); GetClassName(h,c,128); return c.ToString(); }
 public static string Txt(IntPtr h){ var t=new StringBuilder(1024); GetWindowText(h,t,1024); return t.ToString(); }
 public static List<IntPtr> Tops(uint pid){ var r=new List<IntPtr>(); EnumWindows((h,l)=>{ uint p; GetWindowThreadProcessId(h,out p); if(p==pid && IsWindowVisible(h) && Cls(h)=="EVA_Window_Dblclk") r.Add(h); return true;},IntPtr.Zero); return r; }
 public static List<IntPtr> TopsAll(uint pid){ var r=new List<IntPtr>(); EnumWindows((h,l)=>{ uint p; GetWindowThreadProcessId(h,out p); if(p==pid && Cls(h)=="EVA_Window_Dblclk") r.Add(h); return true;},IntPtr.Zero); return r; }
 public static List<IntPtr> Kids(IntPtr w, string cls){ var r=new List<IntPtr>(); EnumChildWindows(w,(h,l)=>{ if(Cls(h).StartsWith(cls)) r.Add(h); return true;},IntPtr.Zero); return r; }
 public static string Get(IntPtr h){ var t=new StringBuilder(4096); SendMessage(h,0x000D,(IntPtr)4096,t); return t.ToString(); }
 public static void Key(IntPtr h, int vk, int scan){ PostMessage(h,0x0100,(IntPtr)vk,(IntPtr)(1|(scan<<16))); PostMessage(h,0x0101,(IntPtr)vk,(IntPtr)(1|(scan<<16)|unchecked((int)0xC0000000))); }
 public static void Wheel(IntPtr h, int delta, int n, int sx, int sy){ IntPtr lp=(IntPtr)(((sy&0xFFFF)<<16)|(sx&0xFFFF)); IntPtr wp=(IntPtr)((delta&0xFFFF)<<16); for(int i=0;i<n;i++){ PostMessage(h,0x020A,wp,lp); System.Threading.Thread.Sleep(40);} }
 public static void DblClick(IntPtr h, int x, int y){ IntPtr lp=(IntPtr)(((y&0xFFFF)<<16)|(x&0xFFFF)); PostMessage(h,0x0200,IntPtr.Zero,lp); System.Threading.Thread.Sleep(60); PostMessage(h,0x0201,(IntPtr)1,lp); PostMessage(h,0x0202,IntPtr.Zero,lp); System.Threading.Thread.Sleep(60); PostMessage(h,0x0203,(IntPtr)1,lp); PostMessage(h,0x0202,IntPtr.Zero,lp); }
 public static bool Restore(IntPtr target){ // 현재 앞 창(카톡)의 입력 권한을 빌려 원래 창을 앞으로
   if(target==IntPtr.Zero || !IsWindow(target)) return false;
   IntPtr fg=GetForegroundWindow(); if(fg==target) return true;
   uint ft=GetWindowThreadProcessId(fg,IntPtr.Zero), me=GetCurrentThreadId();
   AttachThreadInput(me,ft,true); SetForegroundWindow(target); AttachThreadInput(me,ft,false);
   return GetForegroundWindow()==target; }
 public static string Norm(string s){ var b=new StringBuilder(); foreach(char c in s){ if((c>='가'&&c<='힣')||char.IsLetterOrDigit(c)&&c<128) b.Append(char.ToLowerInvariant(c)); } return b.ToString(); }
 public static double Sim(string a, string b){ if(a.Length==0||b.Length==0) return 0; var d=new int[a.Length+1,b.Length+1];
   for(int i=0;i<=a.Length;i++) d[i,0]=i; for(int j=0;j<=b.Length;j++) d[0,j]=j;
   for(int i=1;i<=a.Length;i++) for(int j=1;j<=b.Length;j++){ int c=a[i-1]==b[j-1]?0:1; d[i,j]=Math.Min(Math.Min(d[i-1,j]+1,d[i,j-1]+1),d[i-1,j-1]+c); }
   return 1.0-(double)d[a.Length,b.Length]/Math.Max(a.Length,b.Length); }
}
'@ }
[void][KT]::SetProcessDPIAware()
$script:OcrPs = Join-Path $PSScriptRoot 'ocr.ps1'
$script:kpid = $null
$script:prevFg = [KT]::GetForegroundWindow()

function Restore-Focus { if ([KT]::GetForegroundWindow() -ne $script:prevFg) { [void][KT]::Restore($script:prevFg) } }
function Close-Win([IntPtr]$h) { [void][KT]::PostMessage($h, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) }
function Get-Rect([IntPtr]$h) { $r = New-Object KR; [void][KT]::GetWindowRect($h, [ref]$r); $r }
function Get-Kpid {
  $p = Get-Process KakaoTalk -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $p) { throw '카카오톡 PC가 실행 중이 아님' }
  $script:kpid = [uint32]$p.Id; $script:kpid
}
function Get-Tops { if (-not $script:kpid) { [void](Get-Kpid) }; @([KT]::Tops($script:kpid)) }
$script:MainBack = $null
$script:MainSave = Join-Path $PSScriptRoot '메인창_원위치.txt'
function Save-MainState { $b = $script:MainBack; $mode = if ($b.WasHidden) { 2 } elseif ($b.WasMin) { 1 } else { 0 }; Set-Content -Encoding ASCII $script:MainSave "$mode $($b.L) $($b.T) $($b.R) $($b.B)" }
# 메인 창을 옮겼거나 최소화·숨김을 풀었으면 원래 자리·상태로 되돌린다 (스크립트가 끝나는 모든 경로에서 부른다)
function Leave-Main {
  $b = $script:MainBack; $script:MainBack = $null
  if ($b -and [KT]::IsWindow($b.Win)) {
    if ($b.WasHidden) { [KT]::Place($b.Win, 0, $b.L, $b.T, $b.R, $b.B) }          # 트레이로 닫혀 있던 창은 다시 숨긴다
    elseif ($b.WasMin) { [KT]::Place($b.Win, 7, $b.L, $b.T, $b.R, $b.B) }
    else { [void][KT]::SetWindowPos($b.Win, [IntPtr]::Zero, $b.L, $b.T, ($b.R - $b.L), ($b.B - $b.T), 0x0014) }
  }
  Remove-Item $script:MainSave -Force -ErrorAction SilentlyContinue
}
# 메인 창을 옮기기 전에 원래 자리를 기록한다 (스크립트가 중간에 끊겨도 다음 실행이 되돌린다)
function Hold-Main([IntPtr]$h) {
  if ($script:MainBack) { return }
  $r = Get-Rect $h
  $script:MainBack = @{ Win = $h; WasMin = $false; WasHidden = $false; L = $r.L; T = $r.T; R = $r.R; B = $r.B }
  Save-MainState
}
# 사용자가 지금 카톡 창을 앞에 두고 입력 중이면 건드리지 않는다 (메시지에 '사용 중'이 들어가면 호출 쪽이 다음 회차로 미룬다)
# 다른 프로그램·브라우저를 쓰는 중이거나, 카톡 창이 앞에 있어도 15초 넘게 입력이 없으면 진행한다
function Assert-NotBusy {
  $fg = [KT]::GetForegroundWindow()
  $idle = [math]::Floor([KT]::IdleMs() / 1000)
  if ((@(Get-Tops) -contains $fg) -and $idle -lt 15) { throw "사용 중: 사용자가 카톡 창을 앞에 두고 쓰는 중 (입력 $($idle)초 전)" }
}
function Get-Main {
  $m = @(Get-Tops | Where-Object { [KT]::Txt($_) -ceq '카카오톡' })
  $hidden = $false
  if ($m.Count -eq 0) {   # 창을 닫아 트레이에만 있는 경우: 숨겨진 메인 창을 찾는다
    if (-not $script:kpid) { [void](Get-Kpid) }
    $m = @([KT]::TopsAll($script:kpid) | Where-Object { [KT]::Txt($_) -ceq '카카오톡' })
    $hidden = $true
  }
  if ($m.Count -ne 1) { throw '카카오톡 메인 창을 찾지 못함 (카카오톡이 로그아웃·종료 상태일 수 있음)' }
  $h = $m[0]
  if (-not $script:MainBack -and (Test-Path $script:MainSave)) {   # 이전 실행이 끊겨 창이 화면 밖에 남아 있으면 되돌린다
    $v = @((Get-Content $script:MainSave -Raw).Trim() -split '\s+')
    if ($v.Count -eq 5) { $script:MainBack = @{ Win = $h; WasMin = ($v[0] -eq '1'); WasHidden = ($v[0] -eq '2'); L = [int]$v[1]; T = [int]$v[2]; R = [int]$v[3]; B = [int]$v[4] } }
    Leave-Main
    $hidden = -not [KT]::IsWindowVisible($h)
  }
  if ($hidden -or [KT]::IsIconic($h)) {   # 숨김·최소화 상태면 포커스를 가져오지 않고 화면 밖에서 복원한다. 호출한 쪽이 끝나면 Leave-Main
    $n = [KT]::Normal($h)
    if (($n[2] - $n[0]) -lt 300 -or ($n[3] - $n[1]) -lt 400 -or $n[0] -lt -10000) { $n = @(1221, 94, 1792, 963) }
    $script:MainBack = @{ Win = $h; WasMin = (-not $hidden); WasHidden = $hidden; L = $n[0]; T = $n[1]; R = $n[2]; B = $n[3] }
    Save-MainState
    Add-Type -AssemblyName System.Windows.Forms
    $x = [System.Windows.Forms.SystemInformation]::VirtualScreen.Right + 200
    [KT]::Place($h, 4, $x, 0, ($x + $n[2] - $n[0]), ($n[3] - $n[1]))
    Start-Sleep -Milliseconds 800
  }
  $h
}
function Get-ListView([IntPtr]$main) {
  $lv = @([KT]::Kids($main, 'EVA_Window') | Where-Object { [KT]::Txt($_) -like 'ChatRoomListView_*' })
  if ($lv.Count -ne 1 -or -not [KT]::IsWindowVisible($lv[0])) { throw '메인 창이 채팅 탭이 아님' }
  $lv[0]
}
function Save-Print([IntPtr]$h, [string]$path) { # 가려진 창도 캡처
  $r = Get-Rect $h
  $bmp = New-Object Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
  $g = [Drawing.Graphics]::FromImage($bmp); $dc = $g.GetHdc(); [void][KT]::PrintWindow($h, $dc, 2); $g.ReleaseHdc($dc)
  $bmp.Save($path); $g.Dispose(); $bmp.Dispose(); $path
}
function Invoke-Ocr([string]$path) { # → [pscustomobject]@{X;Y;Text}
  & $script:OcrPs -Path $path | ForEach-Object { $a = $_ -split ' ', 3; if ($a.Count -eq 3) { [pscustomobject]@{ X = [int]$a[0]; Y = [int]$a[1]; Text = $a[2] } } }
}
function Find-RoomWindows([string]$Title) { @(Get-Tops | Where-Object { [KT]::Txt($_) -ceq $Title }) }

# 방 창을 찾거나, 없으면 메인 창 검색으로 연다. → @{ Win; OpenedHere }
# 검색 결과를 OCR로 읽어 제목이 가장 비슷한 줄을 더블클릭한다(첫 줄이 다른 방일 수 있음).
# 열린 창 제목이 정확히 같지 않으면 닫고 실패한다.
function Open-Room([string]$Title, [string]$TmpDir = $env:TEMP) {
  $w = Find-RoomWindows $Title
  if ($w.Count -gt 1) { throw "'$Title' 창이 $($w.Count)개 열려 있음" }
  if ($w.Count -eq 1) { return @{ Win = $w[0]; OpenedHere = $false } }
  $main = Get-Main; $lv = Get-ListView $main
  $search = @([KT]::Kids($lv, 'Edit') | Where-Object { [KT]::GetParent($_) -eq $lv })
  if ($search.Count -ne 1) { throw '채팅방 검색창을 찾지 못함' }
  $search = $search[0]
  Assert-NotBusy
  if (([KT]::Txt($search) + [KT]::Get($search)).Trim()) { throw '사용 중: 카톡 검색창에 글자가 있음' }
  $lc = @([KT]::Kids($lv, 'EVA_VH_ListControl'))[0]
  $before = @(Get-Tops | ForEach-Object { [long]$_ })
  $orig = $null
  # 검색어: 앞의 아이콘(🍋, 보이지 않는 결합 문자 포함)을 떼고 앞 14자만. 맞는 줄은 아래 OCR로 고른다
  $query = ($Title -replace '^[^\p{L}\p{N}]+', '')
  if ($query.Length -gt 14) { $query = $query.Substring(0, 14) }
  [void][KT]::SendMessage($search, 0x000C, [IntPtr]::Zero, $query); Start-Sleep -Milliseconds 900
  try {
    # 검색 결과 줄 고르기
    $shot = Join-Path $TmpDir ('kk_search_' + [guid]::NewGuid().ToString('N') + '.png')
    Save-Print $main $shot | Out-Null
    $mr = Get-Rect $main; $lr = Get-Rect $lc
    $ox = $lr.L - $mr.L; $oy = $lr.T - $mr.T
    $want = [KT]::Norm($Title)
    $best = $null; $bestSim = 0
    foreach ($l in (Invoke-Ocr $shot)) {
      if ($l.Y -lt $oy -or $l.Y -gt ($oy + $lr.B - $lr.T) -or $l.X -lt ($ox + 40) -or $l.X -gt ($ox + 160)) { continue }
      $t = $l.Text -replace '\s+\d{1,3}(\s.*)?$', ''
      $trunc = $t -match '(\.\.\.|…)$'
      $n = [KT]::Norm($t); if ($n.StartsWith('0')) { $n = $n.Substring(1) }
      $cmp = if ($trunc -and $want.Length -gt $n.Length) { $want.Substring(0, $n.Length) } else { $want }
      $sim = [KT]::Sim($n, $cmp)
      if ($sim -gt $bestSim) { $bestSim = $sim; $best = $l }
    }
    Remove-Item $shot -ErrorAction SilentlyContinue
    if ($best -and $bestSim -ge 0.7) { [KT]::DblClick($lc, 200, $best.Y - $oy + 8) }
    else { [KT]::Key($search, 0x28, 0x50); Start-Sleep -Milliseconds 250; [KT]::Key($search, 0x0D, 0x1C) }
    # 창이 늦게 뜨는 경우가 있어 최대 8초 기다린다. 새 창이 생기는 순간(3ms 간격)에 바로 화면 밖으로 옮겨 사용자 화면에 보이지 않게 한다
    Add-Type -AssemblyName System.Windows.Forms
    $offx = [System.Windows.Forms.SystemInformation]::VirtualScreen.Right + 200
    $orect = New-Object KR
    $hw = [KT]::WaitMove($script:kpid, $Title, [long[]]$before, 8000, $offx, [ref]$orect)
    $ok = if ($hw -ne [IntPtr]::Zero) { @($hw) } else { @() }
    if ($ok.Count -eq 1) { $orig = $orect }
    Start-Sleep -Milliseconds 600
    Restore-Focus
  } finally { [void][KT]::SendMessage($search, 0x000C, [IntPtr]::Zero, '') }
  # 이번에 새로 뜬 창 중 목표가 아닌 엉뚱한 방은 닫는다.
  # 사용자가 같은 때 직접 연 창을 닫지 않도록, 입력칸이 '메시지 입력'(비어 있고 포커스 없음)인 대화창만 닫는다.
  $new = @(Get-Tops | Where-Object { $before -notcontains [long]$_ })
  foreach ($h in ($new | Where-Object { [KT]::Txt($_) -cne $Title })) {
    $e = @([KT]::Kids($h, 'RICHEDIT'))
    if ($e.Count -eq 1 -and [KT]::Get($e[0]) -ceq '메시지 입력') { Close-Win $h }
  }
  if ($ok.Count -ne 1) { throw "검색으로 '$Title' 창이 열리지 않음 (열린 창: $(($new | ForEach-Object { [KT]::Txt($_) }) -join ', '))" }
  Start-Sleep -Milliseconds 300; Restore-Focus
  @{ Win = $ok[0]; OpenedHere = $true; Orig = $orig }
}

# 창을 모든 모니터 오른쪽 바깥으로 옮긴다(PrintWindow·창 메시지는 그대로 동작). 원래 위치를 돌려준다.
function Hide-Win([IntPtr]$h) {
  Add-Type -AssemblyName System.Windows.Forms
  $r = Get-Rect $h
  $x = [System.Windows.Forms.SystemInformation]::VirtualScreen.Right + 200
  [void][KT]::SetWindowPos($h, [IntPtr]::Zero, $x, 0, ($r.R - $r.L), ($r.B - $r.T), 0x0014)   # NOZORDER|NOACTIVATE
  $r
}
# Open-Room으로 직접 연 방이면 원래 위치·크기로 되돌린 뒤 닫는다(카톡이 창 위치를 기억하므로). 사용자가 열어 둔 방은 그대로 둔다.
function Close-Room($room) {
  if (-not $room.OpenedHere) { return }
  # 방이 뜨는 순간 포커스를 받아 사용자가 친 글자가 들어갔으면 지운다(직접 연 방은 원래 빈 입력칸이었다)
  $e = @([KT]::Kids($room.Win, 'RICHEDIT'))
  if ($e.Count -eq 1) { $t = [KT]::Get($e[0]); if ($t -and $t -cne '메시지 입력') { [void][KT]::SendMessage($e[0], 0x00B1, [IntPtr]0, [IntPtr](-1)); [void][KT]::SendMessage($e[0], 0x00C2, [IntPtr]1, '') } }
  $o = $room.Orig
  if ($o) {   # 숨긴 채로 원래 자리·크기로 되돌린다(카톡이 닫을 때의 창 위치를 기억하므로). 보이는 상태로 옮기면 화면에 잠깐 나타난다
    [void][KT]::ShowWindow($room.Win, 0)
    [void][KT]::SetWindowPos($room.Win, [IntPtr]::Zero, $o.L, $o.T, ($o.R - $o.L), ($o.B - $o.T), 0x0014)
    Start-Sleep -Milliseconds 80
  }
  # 닫기 요청이 늦게 처리되면 다음 단계가 이 창을 '사용자가 열어 둔 창'으로 착각하므로, 실제로 닫힐 때까지 기다린다
  for ($i = 0; $i -lt 3 -and [KT]::IsWindow($room.Win); $i++) {
    if ($i -ge 1) { [void][KT]::ShowWindow($room.Win, 4) }   # 숨긴 창이 안 닫히면 보이게 한 뒤 다시 닫는다
    Close-Win $room.Win
    for ($j = 0; $j -lt 15 -and [KT]::IsWindow($room.Win); $j++) { Start-Sleep -Milliseconds 100 }
  }
}
