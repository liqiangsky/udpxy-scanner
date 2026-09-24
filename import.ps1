# import.ps1 - 手动恢复 backup.sql 到已运行的数据库（Windows PowerShell）
# 适用场景: 目标机器的 postgres 数据卷已初始化过（自动导入被跳过），需要手动恢复
# 用法: .\import.ps1 [-Y]
param(
    [switch]$Y
)

$ErrorActionPreference = "Stop"

$Container = if ($env:UDXPY_DB_CONTAINER) { $env:UDXPY_DB_CONTAINER } else { "udpxy-scanner-db" }
$DbUser    = "udpxy"
$DbName    = "udpxy"
$Tables    = @("cache", "config", "host", "parameter", "subscription")
$TablesCsv = "cache, config, host, parameter, subscription"

$OutFile = Join-Path $PSScriptRoot "backup.sql"

# 1. 前置检查
$running = @(docker ps --filter "name=$Container" --filter "status=running" --format "{{.Names}}")
if ($running.Trim() -notcontains $Container) {
    Write-Host "[X] 容器 $Container 未在运行。请先: docker compose up -d db" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $OutFile)) {
    Write-Host "[X] 未找到 backup.sql（请把备份文件放到项目根目录）" -ForegroundColor Red
    exit 1
}

# CRLF 校验（字节层）
$bytes = [System.IO.File]::ReadAllBytes($OutFile)
$crlf = 0
for ($i = 0; $i -lt $bytes.Length - 1; $i++) {
    if ($bytes[$i] -eq 13 -and $bytes[$i + 1] -eq 10) { $crlf++ }
}
if ($crlf -ne 0) {
    Write-Host "[X] backup.sql 含 $crlf 处 CRLF 行尾，文件已损坏，请重新导出" -ForegroundColor Red
    exit 1
}

# 2. 抽数据段（COPY 块 + setval）
$lines = [System.IO.File]::ReadAllLines($OutFile)
$sb = New-Object System.Text.StringBuilder
$inCopy = $false
$copyCount = 0
foreach ($line in $lines) {
    if ($line -like "COPY public.*") {
        $copyCount++
        $inCopy = $true
        [void]$sb.AppendLine($line)
    }
    elseif ($inCopy -and $line -eq '\.') {
        [void]$sb.AppendLine($line)
        $inCopy = $false
    }
    elseif ($inCopy) {
        [void]$sb.AppendLine($line)
    }
    elseif ($line -like "SELECT pg_catalog.setval*") {
        [void]$sb.AppendLine($line)
    }
}
if ($copyCount -eq 0) {
    Write-Host "[X] backup.sql 中没有数据段(COPY)，文件无效" -ForegroundColor Red
    exit 1
}

Write-Host "[1/3] backup.sql 校验通过（CRLF=0，数据段=$copyCount）" -ForegroundColor Green

# 3. 数据对比
Write-Host "[2/3] 即将覆盖导入，数据对比（备份 -> 当前）:" -ForegroundColor Yellow
foreach ($t in $Tables) {
    $cur = (docker exec $Container psql -U $DbUser -d $DbName -tAc "SELECT count(*) FROM $t" 2>$null)
    if (-not $cur) { $cur = "?" }
    $backupCount = 0
    $copyLine = $lines | Where-Object { $_ -like "COPY public.$t *" } | Select-Object -First 1
    if ($copyLine) {
        $start = [array]::IndexOf($lines, $copyLine)
        for ($j = $start + 1; $j -lt $lines.Count; $j++) {
            if ($lines[$j] -eq '\.') { break }
            $backupCount++
        }
    }
    Write-Host ("      {0,-14} {1,8} -> {2,-8}" -f $t, $backupCount, $cur)
}

Write-Host ">> 建议先暂停应用再恢复: docker compose stop backend（恢复后 start）" -ForegroundColor Yellow
if (-not $Y) {
    $ans = Read-Host ">> 将清空以上 5 张表并导入备份数据（事务保护，失败自动回滚）。确认? [y/N]"
    if ($ans -ne "y") { Write-Host "已取消"; exit 0 }
}

# 4. 导入（写临时文件，容器内执行；单事务：TRUNCATE+导入要么全成要么全回滚）
$tmpHost = Join-Path $env:TEMP "import_data.sql"
[System.IO.File]::WriteAllText($tmpHost, $sb.ToString(), (New-Object System.Text.UTF8Encoding($false)))
docker cp $tmpHost "${Container}:/tmp/import_data.sql"
if ($LASTEXITCODE -ne 0) { Write-Host "[X] docker cp 失败" -ForegroundColor Red; exit 1 }

# 直接 docker exec 分参传给 psql（不经 sh，避免 PS 5.1 嵌套引号问题）；
# -c 和 -f 同一调用，--single-transaction 把 TRUNCATE+导入包在一个事务里
docker exec $Container psql -U $DbUser -d $DbName -v ON_ERROR_STOP=1 --single-transaction -c "TRUNCATE $TablesCsv RESTART IDENTITY;" -f /tmp/import_data.sql | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "[X] 导入失败（事务已回滚，原数据未动）" -ForegroundColor Red; docker exec $Container rm -f /tmp/import_data.sql | Out-Null; exit 1 }
docker exec $Container rm -f /tmp/import_data.sql | Out-Null
Remove-Item $tmpHost -ErrorAction SilentlyContinue

Write-Host "[3/3] 恢复完成，各表行数:" -ForegroundColor Green
foreach ($t in $Tables) {
    $n = (docker exec $Container psql -U $DbUser -d $DbName -tAc "SELECT count(*) FROM $t")
    Write-Host ("      {0,-14} {1} 行" -f $t, $n)
}
Write-Host ">> 完成。如暂停了 backend，执行 docker compose start backend" -ForegroundColor Cyan
