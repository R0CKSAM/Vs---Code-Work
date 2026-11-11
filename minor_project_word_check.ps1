$ErrorActionPreference = 'Stop'
$projectDir = 'D:\sam\OTT_Audience_Analytics_Minor_Project'
$wordApp = $null
$wordDoc = $null
$verificationRows = @()
try {
    $wordApp = New-Object -ComObject Word.Application
    $wordApp.Visible = $false
    $wordApp.DisplayAlerts = 0
    foreach ($docName in @('01_Project_Synopsis_DRAFT', '02_Project_Report_DRAFT')) {
        $docPath = Join-Path $projectDir ($docName + '.docx')
        $pdfPath = Join-Path $projectDir ($docName + '.pdf')
        $wordDoc = $wordApp.Documents.Open($docPath, $false, $true)
        $wordDoc.Repaginate()
        $verificationRows += [ordered]@{
            document = $docName
            opened_in_word = $true
            pages = $wordDoc.ComputeStatistics(2)
            word_reported_words_including_front_matter_references = $wordDoc.ComputeStatistics(0)
            margins_points = @($wordDoc.PageSetup.TopMargin, $wordDoc.PageSetup.RightMargin, $wordDoc.PageSetup.BottomMargin, $wordDoc.PageSetup.LeftMargin)
            tables = $wordDoc.Tables.Count
        }
        $wordDoc.ExportAsFixedFormat($pdfPath, 17)
        $wordDoc.Close(0)
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($wordDoc)
        $wordDoc = $null
    }
    $verificationRows | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $projectDir 'word_validation.json') -Encoding UTF8
    $verificationRows | ConvertTo-Json -Depth 5
}
finally {
    if ($null -ne $wordDoc) { $wordDoc.Close(0) }
    if ($null -ne $wordApp) {
        $wordApp.Quit()
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($wordApp)
    }
}
