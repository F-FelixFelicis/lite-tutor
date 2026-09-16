$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()

$edgeUrl = if ($args.Count -ge 1 -and $args[0]) {
    $args[0]
} elseif ($env:EDGE_URL) {
    $env:EDGE_URL
} else {
    "http://127.0.0.1:8000"
}
$edgeUrl = $edgeUrl.TrimEnd("/")

function Invoke-PostJson {
    param(
        [string]$Url,
        [object]$Body
    )
    Invoke-RestMethod `
        -Uri $Url `
        -Method Post `
        -ContentType "application/json; charset=utf-8" `
        -Body ($Body | ConvertTo-Json -Depth 8)
}

$results = @()

try {
    $health = Invoke-RestMethod -Uri "$edgeUrl/health" -Method Get
    $results += [pscustomobject]@{
        Check = "Health"
        Ok = $health.status -eq "ok"
        Detail = "llm=$($health.llm_configured) code=$($health.code_execution_enabled)"
    }
} catch {
    $health = $null
    $results += [pscustomobject]@{ Check = "Health"; Ok = $false; Detail = $_.Exception.Message }
}

try {
    $tools = Invoke-RestMethod -Uri "$edgeUrl/tools" -Method Get
    $toolNames = @($tools.tools | ForEach-Object { $_.function.name })
    $required = @("edge_knowledge_rag", "edge_quiz_generator", "edge_answer_grader")
    $hasRequired = ($required | Where-Object { $_ -notin $toolNames }).Count -eq 0
    $computeMatchesHealth = $true
    if ($health) {
        $computeMatchesHealth = (($toolNames -contains "edge_compute_sandbox") -eq [bool]$health.code_execution_enabled)
    }
    $results += [pscustomobject]@{
        Check = "Tools"
        Ok = $hasRequired -and $computeMatchesHealth
        Detail = ($toolNames -join ",")
    }
} catch {
    $results += [pscustomobject]@{ Check = "Tools"; Ok = $false; Detail = $_.Exception.Message }
}

foreach ($mode in @("hybrid", "vector")) {
    try {
        $resp = Invoke-PostJson -Url "$edgeUrl/search" -Body @{
            query = "KMP algorithm"
            mode = $mode
            n_results = 2
        }
        $results += [pscustomobject]@{
            Check = "Search $mode"
            Ok = ($resp.status -eq "success") -and (-not $resp.fallback_required) -and [bool]$resp.context
            Detail = "fallback=$($resp.fallback_required) conf=$($resp.confidence)"
        }
    } catch {
        $results += [pscustomobject]@{ Check = "Search $mode"; Ok = $false; Detail = $_.Exception.Message }
    }
}

try {
    $resp = Invoke-PostJson -Url "$edgeUrl/solve" -Body @{
        code = "print(2**10)"
        language = "python"
        timeout = 5
    }
    if ($health -and $health.code_execution_enabled) {
        $okSolve = ($resp.status -eq "success") -and ($resp.stdout -match "1024")
    } else {
        $okSolve = $resp.status -eq "disabled"
    }
    $results += [pscustomobject]@{ Check = "Solve policy"; Ok = $okSolve; Detail = $resp.status }
} catch {
    $results += [pscustomobject]@{ Check = "Solve policy"; Ok = $false; Detail = $_.Exception.Message }
}

try {
    $resp = Invoke-PostJson -Url "$edgeUrl/quiz" -Body @{
        question = "DFS basics"
        n_results = 2
        difficulty = "medium"
        question_type = "choice"
    }
    $okQuiz = ($resp.status -eq "success") -and [bool]$resp.quiz -and ($resp.question_type -eq "choice")
    $results += [pscustomobject]@{ Check = "Quiz fallback"; Ok = $okQuiz; Detail = $resp.status }
} catch {
    $results += [pscustomobject]@{ Check = "Quiz fallback"; Ok = $false; Detail = $_.Exception.Message }
}

try {
    $resp = Invoke-PostJson -Url "$edgeUrl/grade" -Body @{
        answer = "A"
        question = "Choice smoke test"
        question_type = "choice"
        expected_answer = "A"
        session_id = "smoke-test"
    }
    $okGrade = ($resp.status -eq "success") -and ($resp.matched_keywords -contains "A")
    $results += [pscustomobject]@{ Check = "Objective grade"; Ok = $okGrade; Detail = $resp.result }
} catch {
    $results += [pscustomobject]@{ Check = "Objective grade"; Ok = $false; Detail = $_.Exception.Message }
}

try {
    $start = Invoke-PostJson -Url "$edgeUrl/tutor" -Body @{ user_input = "KMP algorithm" }
    $session = $start.session_id
    $explain = Invoke-PostJson -Url "$edgeUrl/tutor" -Body @{
        session_id = $session
        user_input = "I do not understand the next array"
    }
    $quiz = Invoke-PostJson -Url "$edgeUrl/tutor" -Body @{
        session_id = $session
        user_input = "continue"
    }
    $grade = Invoke-PostJson -Url "$edgeUrl/tutor" -Body @{
        session_id = $session
        user_input = "KMP reduces repeated comparisons with a partial match table"
    }
    $okTutor = ($start.stage -eq "diagnose") -and
        ($explain.stage -eq "explain") -and
        ($quiz.stage -eq "quiz") -and
        ($grade.stage -eq "validate")
    $results += [pscustomobject]@{
        Check = "Tutor FSM"
        Ok = $okTutor
        Detail = "$($start.stage)->$($explain.stage)->$($quiz.stage)->$($grade.stage)"
    }
} catch {
    $results += [pscustomobject]@{ Check = "Tutor FSM"; Ok = $false; Detail = $_.Exception.Message }
}

Write-Host ""
Write-Host "Edge URL: $edgeUrl"
Write-Host ""
$results | Format-Table -AutoSize
Write-Host ""

$failed = @($results | Where-Object { -not $_.Ok })
if ($failed.Count -eq 0) {
    Write-Host "All checks passed."
    exit 0
}

Write-Host "$($failed.Count) check(s) failed."
exit 1
