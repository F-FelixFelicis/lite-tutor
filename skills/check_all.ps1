$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()

$edgeUrl = if ($args.Count -ge 1 -and $args[0]) { $args[0] } elseif ($env:EDGE_URL) { $env:EDGE_URL } else { "http://127.0.0.1:8000" }
$edgeUrl = $edgeUrl.TrimEnd("/")

function Invoke-PostJson {
    param(
        [string]$Url,
        [object]$Body
    )
    return Invoke-RestMethod -Uri $Url -Method Post -ContentType "application/json; charset=utf-8" -Body ($Body | ConvertTo-Json -Depth 8)
}

$results = @()

try {
    $tools = Invoke-RestMethod -Uri "$edgeUrl/tools" -Method Get
    $toolNames = @()
    if ($tools.tools) {
        $toolNames = $tools.tools | ForEach-Object { $_.function.name }
    }
    $okTools = ($toolNames -contains "edge_compute_sandbox") -and ($toolNames -contains "edge_knowledge_rag") -and ($toolNames -contains "edge_quiz_generator") -and ($toolNames -contains "edge_answer_grader")
    $results += [pscustomobject]@{ Check = "Tools"; Ok = $okTools; Detail = ($toolNames -join ",") }
} catch {
    $results += [pscustomobject]@{ Check = "Tools"; Ok = $false; Detail = $_.Exception.Message }
}

try {
    $payload = @{ query = "KMP 是什么"; mode = "hybrid"; n_results = 2 }
    $resp = Invoke-PostJson -Url "$edgeUrl/search" -Body $payload
    $okSearch = ($resp.status -eq "success") -and ($resp.context -and $resp.context.Length -gt 0)
    $results += [pscustomobject]@{ Check = "Search Hybrid"; Ok = $okSearch; Detail = "$($resp.status) fallback=$($resp.fallback_required) conf=$($resp.confidence)" }
} catch {
    $results += [pscustomobject]@{ Check = "Search Hybrid"; Ok = $false; Detail = $_.Exception.Message }
}

try {
    $payload = @{ query = "KMP 是什么"; mode = "vector"; n_results = 2 }
    $resp = Invoke-PostJson -Url "$edgeUrl/search" -Body $payload
    $okSearch = ($resp.status -eq "success") -and ($resp.context -and $resp.context.Length -gt 0)
    $results += [pscustomobject]@{ Check = "Search Vector"; Ok = $okSearch; Detail = "$($resp.status) fallback=$($resp.fallback_required) conf=$($resp.confidence)" }
} catch {
    $results += [pscustomobject]@{ Check = "Search Vector"; Ok = $false; Detail = $_.Exception.Message }
}

try {
    $payload = @{ code = "print(2**10)"; language = "python"; timeout = 10 }
    $resp = Invoke-PostJson -Url "$edgeUrl/solve" -Body $payload
    $okSolve = ($resp.status -eq "success") -and ($resp.stdout -match "1024")
    $results += [pscustomobject]@{ Check = "Solve Code"; Ok = $okSolve; Detail = $resp.status }
} catch {
    $results += [pscustomobject]@{ Check = "Solve Code"; Ok = $false; Detail = $_.Exception.Message }
}

try {
    $payload = @{ question = "什么是DFS?"; n_results = 2 }
    $resp = Invoke-PostJson -Url "$edgeUrl/quiz" -Body $payload
    $okQuiz = ($resp.status -eq "success") -and ($resp.quiz -and $resp.quiz.Length -gt 0)
    $results += [pscustomobject]@{ Check = "Quiz"; Ok = $okQuiz; Detail = $resp.status }
} catch {
    $results += [pscustomobject]@{ Check = "Quiz"; Ok = $false; Detail = $_.Exception.Message }
}

try {
    $payload = @{ answer = "使用 栈 遍历"; keywords = @("栈","回溯"); min_hit = 1 }
    $resp = Invoke-PostJson -Url "$edgeUrl/grade" -Body $payload
    $okGrade = ($resp.status -eq "success") -and ($resp.result -eq "校验通过")
    $results += [pscustomobject]@{ Check = "Grade"; Ok = $okGrade; Detail = $resp.result }
} catch {
    $results += [pscustomobject]@{ Check = "Grade"; Ok = $false; Detail = $_.Exception.Message }
}

try {
    $start = Invoke-PostJson -Url "$edgeUrl/tutor" -Body @{ user_input = "KMP 是什么" }
    $session = $start.session_id
    $s1 = Invoke-PostJson -Url "$edgeUrl/tutor" -Body @{ session_id = $session; user_input = "我不太理解 next 数组" }
    $s2 = Invoke-PostJson -Url "$edgeUrl/tutor" -Body @{ session_id = $session; user_input = "继续测验" }
    $s3 = Invoke-PostJson -Url "$edgeUrl/tutor" -Body @{ session_id = $session; user_input = "KMP 通过部分匹配表避免回溯" }
    $okTutor = ($start.stage -eq "diagnose") -and ($s1.stage -eq "explain") -and ($s2.stage -eq "quiz") -and ($s3.stage -eq "validate")
    $results += [pscustomobject]@{ Check = "Tutor FSM"; Ok = $okTutor; Detail = "$($start.stage)->$($s1.stage)->$($s2.stage)->$($s3.stage)" }
} catch {
    $results += [pscustomobject]@{ Check = "Tutor FSM"; Ok = $false; Detail = $_.Exception.Message }
}

$allOk = $results | ForEach-Object { $_.Ok } | Where-Object { $_ -eq $false }
Write-Host ""
Write-Host "Edge URL: $edgeUrl"
Write-Host ""
$results | Format-Table -AutoSize
Write-Host ""
if ($allOk.Count -eq 0) {
    Write-Host "All checks passed."
} else {
    Write-Host "Some checks failed."
}
