# 이미지 파일을 Windows 한국어 OCR로 읽어 줄 단위로 출력한다: "x y 텍스트"
param([Parameter(Mandatory)][string]$Path, [double]$Scale = 2.0)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime, System.Drawing
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [type]$t) { $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op)); $task.Wait(); $task.Result }

# 작은 글씨 인식률을 위해 확대한 사본으로 읽는다
$src = [Drawing.Image]::FromFile((Resolve-Path $Path))
$big = New-Object Drawing.Bitmap ([int]($src.Width * $Scale)), ([int]($src.Height * $Scale))
$g = [Drawing.Graphics]::FromImage($big); $g.InterpolationMode = 'HighQualityBicubic'; $g.DrawImage($src, 0, 0, $big.Width, $big.Height)
$tmp = Join-Path $env:TEMP ("ocr_" + [guid]::NewGuid().ToString('N') + '.png'); $big.Save($tmp); $g.Dispose(); $big.Dispose(); $src.Dispose()
try {
  $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($tmp)) ([Windows.Storage.StorageFile])
  $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
  $dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
  $bmp = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
  $eng = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('ko'))
  $res = Await ($eng.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
  foreach ($l in $res.Lines) {
    $w = @($l.Words | ForEach-Object { $_ }); $x = [int]($w[0].BoundingRect.X / $Scale); $y = [int]($w[0].BoundingRect.Y / $Scale)
    # 한글 OCR은 글자 사이를 띄워 돌려주는 경우가 있어, 단어 사이 간격이 좁으면 붙인다
    $sb = New-Object Text.StringBuilder; $prev = $null
    foreach ($wd in $w) {
      if ($prev) { $gap = $wd.BoundingRect.X - ($prev.BoundingRect.X + $prev.BoundingRect.Width); if ($gap -gt ($wd.BoundingRect.Height * 0.25)) { [void]$sb.Append(' ') } }
      [void]$sb.Append($wd.Text); $prev = $wd
    }
    "{0} {1} {2}" -f $x, $y, $sb.ToString()
  }
  $stream.Dispose()
} finally { Remove-Item $tmp -ErrorAction SilentlyContinue }
