# export.ps1 - 一键导出 udpxy-scanner 数据库数据到 backup.sql
# 用法: 在项目根目录执行  .\export.ps1
# 流程: 容器内 pg_dump -> docker cp 拷出 -> 自动校验（CRLF / 数据段 / 各表行数）

$ErrorActionPreference = "Stop"

$Container = "udpxy-scanner-db"
$DbUser    = "udpxy"
$DbName    = "udpxy"
$OutFile   = Join-Path $PSScriptRoot "backup.sql"

# 1. 检查容器是否在运行
$running = @(docker ps --filter "name=$Container" --filter "status=running" --format "{{.Names}}")
if ($running.Trim() -notcontains $Container) {
    Write-Host "[X] 容器 $Container 未在运行。请先执行: docker compose up -d db" -ForegroundColor Red
    exit 1
}

Write-Host "[1/3] 正在导出 $Container -> backup.sql ..."

# 2. 容器内导出（避开 PowerShell 文本管道的 CRLF/编码污染），docker cp 原样拷出
docker exec $Container sh -c "pg_dump -U $DbUser --no-owner --no-privileges -d $DbName > /tmp/backup.sql"
if ($LASTEXITCODE -ne 0) { Write-Host "[X] pg_dump 执行失败" -ForegroundColor Red; exit 1 }

docker cp "${Container}:/tmp/backup.sql" $OutFile
if ($LASTEXITCODE -ne 0) { Write-Host "[X] docker cp 失败" -ForegroundColor Red; exit 1 }
docker exec $Container rm -f /tmp/backup.sql | Out-Null

# 3. 校验（字节层查 CRLF，避免编码转换干扰）
$bytes = [System.IO.File]::ReadAllBytes($OutFile)
$crlf = 0
for ($i = 0; $i -lt $bytes.Length - 1; $i++) {
    if ($bytes[$i] -eq 13 -and $bytes[$i + 1] -eq 10) { $crlf++ }
}
$lines     = [System.IO.File]::ReadAllLines($OutFile)
$copyLines = @($lines | Where-Object { $_ -like "COPY public.*" })

Write-Host "[2/3] 导出完成: $OutFile ($([math]::Round($bytes.Length / 1KB, 1)) KB)" -ForegroundColor Green

if ($crlf -ne 0) {
    Write-Host "[X] 校验失败: 检测到 $crlf 处 CRLF 行尾，数据会被污染，请勿使用该文件" -ForegroundColor Red
    exit 1
}
if ($copyLines.Count -eq 0) {
    Write-Host "[X] 校验失败: 未发现数据段(COPY)，请检查数据库里是否有数据" -ForegroundColor Red
    exit 1
}

# 4. 各表行数统计
Write-Host "[3/3] 校验通过: CRLF=0, 数据段=$($copyLines.Count)，各表行数:" -ForegroundColor Green
foreach ($copyLine in $copyLines) {
    $table = ($copyLine -split ' ')[1] -replace 'public\.', ''
    $start = [array]::IndexOf($lines, $copyLine)
    $count = 0
    for ($j = $start + 1; $j -lt $lines.Count; $j++) {
        if ($lines[$j] -eq '\.') { break }
        $count++
    }
    Write-Host ("      {0,-14} {1} 行" -f $table, $count)
}

Write-Host ""
Write-Host ">> 把 backup.sql 拷到目标电脑的项目根目录，首次 docker compose up -d 会自动导入。" -ForegroundColor Cyan
